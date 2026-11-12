import logging
from typing import Optional
from fastapi import HTTPException, status
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.enums import TicketStatus, UserRole
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.user import UserAdminCreate, UserCreate

logger = logging.getLogger("helpdesk_api")


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Retrieve a user by their email address."""
    return db.scalars(sa.select(User).where(User.email == email)).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """Retrieve a user by their primary key id."""
    return db.get(User, user_id)


def get_all_users(db: Session, skip: int = 0, limit: int = 100) -> list[User]:
    """Retrieve a list of all users."""
    return list(db.scalars(sa.select(User).offset(skip).limit(limit)).all())


def get_admin_users(
    db: Session,
    q: Optional[str] = None,
    role: Optional[UserRole] = None,
    is_active: Optional[bool] = None,
    skip: Optional[int] = None,
    limit: Optional[int] = None,
) -> tuple[list[dict], int, int]:
    """
    Retrieve users with optional filters (q, role, is_active), computing
    open_assigned_count per user, alongside total and active counts.
    """
    open_tickets_subq = (
        sa.select(sa.func.count(Ticket.id))
        .where(
            Ticket.assignee_id == User.id,
            Ticket.status.notin_([TicketStatus.RESOLVED, TicketStatus.CLOSED]),
        )
        .correlate(User)
        .scalar_subquery()
    )

    conditions = []
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        conditions.append(
            sa.or_(
                sa.func.lower(User.full_name).like(term),
                sa.func.lower(User.email).like(term),
            )
        )
    if role:
        conditions.append(User.role == role)
    if is_active is not None:
        conditions.append(User.is_active == is_active)

    stmt = sa.select(User, open_tickets_subq.label("open_assigned_count")).order_by(
        User.created_at.asc(), User.id.asc()
    )
    if conditions:
        stmt = stmt.where(sa.and_(*conditions))

    if skip is not None:
        stmt = stmt.offset(skip)
    if limit is not None:
        stmt = stmt.limit(limit)

    rows = db.execute(stmt).all()

    # Calculate totals
    count_stmt = sa.select(sa.func.count(User.id))
    active_stmt = sa.select(sa.func.count(User.id)).where(User.is_active.is_(True))

    if conditions:
        count_stmt = count_stmt.where(sa.and_(*conditions))
        active_stmt = active_stmt.where(sa.and_(*conditions))

    total = db.scalar(count_stmt) or 0
    active = db.scalar(active_stmt) or 0

    items = []
    for user_obj, open_count in rows:
        items.append({
            "id": user_obj.id,
            "email": user_obj.email,
            "full_name": user_obj.full_name,
            "role": user_obj.role,
            "is_active": user_obj.is_active,
            "created_at": user_obj.created_at,
            "open_assigned_count": open_count or 0,
        })

    return items, total, active


def register_user(db: Session, user_in: UserCreate) -> User:
    """
    Business rule for user registration:
    - Email must be unique (case-insensitively, returns 409 Conflict if already taken).
    - Public registration always assigns the 'requester' role.
    - Password is securely hashed using bcrypt.
    """
    email_clean = user_in.email.strip().lower()
    existing_user = db.scalars(sa.select(User).where(sa.func.lower(User.email) == email_clean)).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=email_clean,
        full_name=user_in.full_name.strip(),
        hashed_password=hash_password(user_in.password),
        role=UserRole.REQUESTER,
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Concurrent request registered the same email between the check and insert.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    db.refresh(user)
    return user


def create_admin_user(db: Session, user_in: UserAdminCreate, actor_id: int) -> tuple[User, int]:
    """
    Create a new user by an admin:
    - Email trimmed and lowercased, unique case-insensitively (409 if taken).
    - Role assigned per user_in.role.
    - Password hashed with bcrypt.
    - Audit log recorded without passwords or hashes.
    """
    email_clean = user_in.email.strip().lower()
    existing_user = db.scalars(sa.select(User).where(sa.func.lower(User.email) == email_clean)).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=email_clean,
        full_name=user_in.full_name.strip(),
        hashed_password=hash_password(user_in.password),
        role=user_in.role,
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Concurrent request registered the same email between the check and insert.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    db.refresh(user)

    logger.info(
        "Admin action: actor_id=%s target_id=%s action=create old_value=None new_value=%s",
        actor_id,
        user.id,
        {"email": user.email, "role": user.role.value, "full_name": user.full_name},
    )

    return user, 0


def authenticate_user(db: Session, email: str, password: str) -> User:
    """
    Business rule for user login:
    - Verifies user credentials.
    - Fails with 401 Unauthorized if email or password does not match.
    - Fails with 401 Unauthorized if account is inactive.
    """
    email_clean = email.strip().lower()
    user = db.scalars(sa.select(User).where(sa.func.lower(User.email) == email_clean)).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def update_user_role(db: Session, user_id: int, new_role: UserRole, actor_id: Optional[int] = None) -> User:
    """
    Business rule for updating a user's role:
    - Fails with 404 Not Found if user doesn't exist.
    - Fails with 400 Bad Request if admin targets themselves.
    - Fails with 400 Bad Request if demoting the last active admin.
    - Updates role and logs audit action.
    """
    user = get_user_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if actor_id is not None and user.id == actor_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own role",
        )

    if user.role == UserRole.ADMIN and new_role != UserRole.ADMIN and user.is_active:
        active_admin_count = (
            db.scalar(
                sa.select(sa.func.count(User.id)).where(
                    User.role == UserRole.ADMIN,
                    User.is_active.is_(True),
                )
            )
            or 0
        )
        if active_admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the last active admin",
            )

    old_role = user.role.value
    user.role = new_role
    db.commit()
    db.refresh(user)

    logger.info(
        "Admin action: actor_id=%s target_id=%s action=role_change old_value=%s new_value=%s",
        actor_id,
        user.id,
        old_role,
        new_role.value,
    )
    return user


def update_user_status(db: Session, user_id: int, new_is_active: bool, actor_id: Optional[int] = None) -> User:
    """
    Business rule for deactivating/reactivating a user:
    - Fails with 404 Not Found if user doesn't exist.
    - Fails with 400 Bad Request if admin targets themselves.
    - Fails with 400 Bad Request if deactivating the last active admin.
    - Updates is_active and logs audit action.
    """
    user = get_user_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if actor_id is not None and user.id == actor_id:
        action_name = "deactivate" if not new_is_active else "reactivate"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot {action_name} your own account",
        )

    if not new_is_active and user.role == UserRole.ADMIN and user.is_active:
        active_admin_count = (
            db.scalar(
                sa.select(sa.func.count(User.id)).where(
                    User.role == UserRole.ADMIN,
                    User.is_active.is_(True),
                )
            )
            or 0
        )
        if active_admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate the last active admin",
            )

    old_status = user.is_active
    user.is_active = new_is_active
    db.commit()
    db.refresh(user)

    action = "deactivate" if not new_is_active else "reactivate"
    logger.info(
        "Admin action: actor_id=%s target_id=%s action=%s old_value=%s new_value=%s",
        actor_id,
        user.id,
        action,
        old_status,
        new_is_active,
    )
    return user
