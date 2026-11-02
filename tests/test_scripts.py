from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.models.user import User
from app.scripts.create_admin import create_admin
from app.services.users import get_user_by_email


def test_create_admin_script(db_session: Session):
    """Test create_admin creates a new user with ADMIN role."""
    create_admin(
        email="cli_admin@example.com",
        full_name="CLI Admin",
        password="adminpassword123",
        db=db_session,
    )

    user = get_user_by_email(db_session, "cli_admin@example.com")
    assert user is not None
    assert user.role == UserRole.ADMIN
    assert user.full_name == "CLI Admin"
    assert user.is_active is True


def test_create_admin_promotes_existing_user(db_session: Session, requester_user: User):
    """Test create_admin promotes an existing requester to admin."""
    create_admin(
        email=requester_user.email,
        full_name="Ignored",
        password="Ignored",
        db=db_session,
    )

    db_session.refresh(requester_user)
    assert requester_user.role == UserRole.ADMIN


def test_create_admin_already_admin(db_session: Session, admin_user: User):
    """Test create_admin when user is already admin."""
    create_admin(
        email=admin_user.email,
        full_name="Ignored",
        password="Ignored",
        db=db_session,
    )

    db_session.refresh(admin_user)
    assert admin_user.role == UserRole.ADMIN
