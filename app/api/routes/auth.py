import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.demo import DEMO_USERS
from app.core.rate_limit import login_rate_limiter, register_rate_limiter
from app.api.deps import get_current_user
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.token import (
    DemoAccountRead,
    DemoAccountsResponse,
    DemoLoginRequest,
    Token,
)
from app.schemas.user import UserCreate, UserLogin, UserRead
from app.services.users import authenticate_user, get_user_by_email, register_user

logger = logging.getLogger("helpdesk_api")

router = APIRouter(prefix="/auth", tags=["auth"])

_DEMO_ROLE_DESCRIPTIONS = {
    UserRole.REQUESTER: "Raise tickets, track status, and view resolution updates.",
    UserRole.AGENT: "Triage incoming tickets, manage SLAs, and communicate resolutions.",
    UserRole.ADMIN: "Manage users, configure settings, and view system reports.",
}


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
def register(
    user_in: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> UserRead:
    """
    Register a new user account. Defaults to requester role.
    Rate limited per client IP (HTTP 429 when exceeded).
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    register_rate_limiter.check(client_ip)
    user = register_user(db, user_in=user_in)
    return user


@router.post(
    "/login",
    response_model=Token,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and receive a JWT access token",
)
def login(
    credentials: UserLogin,
    request: Request,
    db: Session = Depends(get_db),
) -> Token:
    """
    Authenticate with email and password, returning a signed JWT access token.

    Security & Rate Limiting:
    - Keyed by (normalised_email, client_ip).
    - Failed attempts are tracked in a sliding window.
    - Exceeding the maximum allowed failed attempts results in an HTTP 429 lockout.
    - Uses `request.client.host` directly (does NOT trust X-Forwarded-For).
      Behind a reverse proxy, trusted proxy middleware must configure `request.client`.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"

    # Pre-check lockout before checking credentials
    login_rate_limiter.check_and_raise_if_locked(credentials.email, client_ip)

    try:
        user = authenticate_user(db, email=credentials.email, password=credentials.password)
    except HTTPException:
        login_rate_limiter.record_failure(credentials.email, client_ip)
        raise

    # Reset failure counter on successful authentication
    login_rate_limiter.reset(credentials.email, client_ip)
    access_token = create_access_token(data={"sub": str(user.id), "tv": user.token_version})
    return Token(access_token=access_token, token_type="bearer")


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sign out and invalidate all of the user's access tokens",
)
def logout(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """
    Invalidate every access token issued to the current user so far (including this one).
    The user can sign in again to get a fresh token.
    """
    current_user.token_version += 1
    db.commit()


@router.get(
    "/demo-accounts",
    response_model=DemoAccountsResponse,
    status_code=status.HTTP_200_OK,
    summary="List available demo accounts (DEMO_MODE only)",
)
def get_demo_accounts() -> DemoAccountsResponse:
    """
    Returns available demo accounts when DEMO_MODE is enabled.
    Returns empty accounts list and enabled=false when DEMO_MODE is off.
    Never returns emails or passwords.
    """
    if not settings.DEMO_MODE:
        return DemoAccountsResponse(enabled=False, accounts=[])

    role_order = [UserRole.REQUESTER, UserRole.AGENT, UserRole.ADMIN]
    accounts: list[DemoAccountRead] = []
    for role in role_order:
        user_def = next((u for u in DEMO_USERS if u["role"] == role), None)
        if user_def:
            accounts.append(
                DemoAccountRead(
                    role=role.value,
                    name=user_def["full_name"],
                    description=_DEMO_ROLE_DESCRIPTIONS.get(role, "Sample demo user."),
                )
            )
    return DemoAccountsResponse(enabled=True, accounts=accounts)


@router.post(
    "/demo-login",
    response_model=Token,
    status_code=status.HTTP_200_OK,
    summary="Sign in as a seeded demo user (DEMO_MODE only)",
)
def demo_login(
    payload: DemoLoginRequest,
    db: Session = Depends(get_db),
) -> Token:
    """
    Sign in as a seeded demo account by role without requiring a password.
    Only available when DEMO_MODE is true.
    Bypasses password rate limiting.
    Only logs in the fixed seeded demo users, never arbitrary users.
    """
    if not settings.DEMO_MODE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demo mode is disabled",
        )

    demo_def = next((u for u in DEMO_USERS if u["role"].value == payload.role.value), None)
    if not demo_def:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Demo user for role '{payload.role.value}' is not configured.",
        )

    user = get_user_by_email(db, email=demo_def["email"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Seeded demo user '{demo_def['full_name']}' ({payload.role.value}) does not exist in the database. "
                "Please run seed_demo to initialize demo accounts."
            ),
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Demo account '{user.email}' is inactive and cannot be signed into.",
        )

    if user.role != payload.role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Demo account '{user.email}' role has changed from '{payload.role.value}' to '{user.role.value}'.",
        )

    access_token = create_access_token(data={"sub": str(user.id), "tv": user.token_version})
    return Token(access_token=access_token, token_type="bearer")
