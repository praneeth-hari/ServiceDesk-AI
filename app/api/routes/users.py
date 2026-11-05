from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.user import (
    UserAdminCreate,
    UserAdminRead,
    UserListResponse,
    UserRead,
    UserRoleUpdate,
    UserStatusUpdate,
)
from app.services.users import (
    create_admin_user,
    get_admin_users,
    get_all_users,
    update_user_role,
    update_user_status,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Get current user profile",
)
def get_me(current_user: User = Depends(get_current_user)) -> UserRead:
    """
    Return the profile details of the currently authenticated user.
    """
    return current_user


@router.get(
    "/admin",
    response_model=UserListResponse,
    status_code=status.HTTP_200_OK,
    summary="List users with admin filters and metrics (Admin only)",
)
def list_admin_users(
    q: Optional[str] = Query(None, description="Search term for name or email"),
    role: Optional[UserRole] = Query(None, description="Filter by user role"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    skip: Optional[int] = Query(None, ge=0),
    limit: Optional[int] = Query(None, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles([UserRole.ADMIN])),
) -> UserListResponse:
    """
    List users with optional search and filters, computing open assigned ticket counts,
    total counts, and active counts. Admin only.
    """
    items, total_count, active_count = get_admin_users(
        db,
        q=q,
        role=role,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )
    return UserListResponse(
        rows=items,
        users=items,
        total=total_count,
        active_count=active_count,
        active=active_count,
    )


@router.get(
    "",
    response_model=list[UserRead],
    status_code=status.HTTP_200_OK,
    summary="List all users (Admin only)",
)
def list_users(
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles([UserRole.ADMIN])),
) -> list[User]:
    """
    List all registered users in the system. Requires Admin role.
    Returns flat list of users and sets X-Total-Count and X-Active-Count response headers.
    """
    total = db.scalar(sa.select(sa.func.count(User.id))) or 0
    active = db.scalar(sa.select(sa.func.count(User.id)).where(User.is_active.is_(True))) or 0
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Active-Count"] = str(active)
    return get_all_users(db, skip=skip, limit=limit)


@router.post(
    "",
    response_model=UserAdminRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user (Admin only)",
)
def create_user(
    user_in: UserAdminCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
) -> Any:
    """
    Create a new user with assigned role. Admin only.
    """
    user, open_count = create_admin_user(db, user_in=user_in, actor_id=current_user.id)
    return UserAdminRead(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        open_assigned_count=open_count,
    )


@router.patch(
    "/{id}/role",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Update user role (Admin only)",
)
def update_role(
    id: int,
    role_in: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
) -> UserRead:
    """
    Update the role of an existing user. Admin only.
    Cannot target yourself or demote the last active admin.
    """
    return update_user_role(db, user_id=id, new_role=role_in.role, actor_id=current_user.id)


@router.patch(
    "/{id}/status",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Update user active status (Admin only)",
)
def update_status(
    id: int,
    status_in: UserStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
) -> UserRead:
    """
    Deactivate or reactivate an existing user. Admin only.
    Cannot target yourself or deactivate the last active admin.
    """
    return update_user_status(db, user_id=id, new_is_active=status_in.is_active, actor_id=current_user.id)
