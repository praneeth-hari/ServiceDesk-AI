from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.user import UserRead, UserRoleUpdate
from app.services.users import get_all_users, update_user_role

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
    "",
    response_model=list[UserRead],
    status_code=status.HTTP_200_OK,
    summary="List all users (Admin only)",
)
def list_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles([UserRole.ADMIN])),
) -> list[UserRead]:
    """
    List all registered users in the system. Requires Admin role.
    """
    return get_all_users(db, skip=skip, limit=limit)


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
    _: User = Depends(require_roles([UserRole.ADMIN])),
) -> UserRead:
    """
    Update the role of an existing user. Requires Admin role.
    """
    return update_user_role(db, user_id=id, new_role=role_in.role)
