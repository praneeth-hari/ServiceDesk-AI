from typing import Optional
from fastapi import HTTPException, status
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.user import UserCreate


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Retrieve a user by their email address."""
    return db.scalars(sa.select(User).where(User.email == email)).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """Retrieve a user by their primary key id."""
    return db.get(User, user_id)


def get_all_users(db: Session, skip: int = 0, limit: int = 100) -> list[User]:
    """Retrieve a list of all users."""
    return list(db.scalars(sa.select(User).offset(skip).limit(limit)).all())


def register_user(db: Session, user_in: UserCreate) -> User:
    """
    Business rule for user registration:
    - Email must be unique (returns 409 Conflict if already taken).
    - Public registration always assigns the 'requester' role.
    - Password is securely hashed using bcrypt.
    """
    existing_user = get_user_by_email(db, email=user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=hash_password(user_in.password),
        role=UserRole.REQUESTER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User:
    """
    Business rule for user login:
    - Verifies user credentials.
    - Fails with 401 Unauthorized if email or password does not match.
    - Fails with 401 Unauthorized if account is inactive.
    """
    user = get_user_by_email(db, email=email)
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


def update_user_role(db: Session, user_id: int, new_role: UserRole) -> User:
    """
    Business rule for updating a user's role:
    - Fails with 404 Not Found if user doesn't exist.
    - Updates role and commits changes.
    """
    user = get_user_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.role = new_role
    db.commit()
    db.refresh(user)
    return user
