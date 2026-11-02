import argparse
import getpass
import sys
from typing import Optional
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.enums import UserRole
from app.models.user import User
from app.services.users import get_user_by_email


def _create_or_promote_admin(db: Session, email: str, full_name: str, password: str) -> None:
    user = get_user_by_email(db, email=email)
    if user:
        if user.role == UserRole.ADMIN:
            print(f"User '{email}' is already an admin.")
            return
        user.role = UserRole.ADMIN
        db.commit()
        print(f"Promoted existing user '{email}' to admin role.")
        return

    admin_user = User(
        email=email,
        full_name=full_name,
        hashed_password=hash_password(password),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(admin_user)
    db.commit()
    print(f"Admin user '{email}' created successfully.")


def create_admin(
    email: str,
    full_name: str,
    password: str,
    db: Optional[Session] = None,
) -> None:
    """Create an admin user or promote an existing user to admin."""
    if db is not None:
        _create_or_promote_admin(db, email=email, full_name=full_name, password=password)
    else:
        with SessionLocal() as session:
            _create_or_promote_admin(session, email=email, full_name=full_name, password=password)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first admin user.")
    parser.add_argument("--email", type=str, help="Admin email address")
    parser.add_argument("--full-name", type=str, help="Admin full name")
    parser.add_argument("--password", type=str, help="Admin password")

    args = parser.parse_args()

    email = args.email or input("Admin Email: ").strip()
    if not email:
        print("Error: Email is required.", file=sys.stderr)
        sys.exit(1)

    full_name = args.full_name or input("Admin Full Name: ").strip()
    if not full_name:
        print("Error: Full name is required.", file=sys.stderr)
        sys.exit(1)

    password = args.password or getpass.getpass("Admin Password: ").strip()
    if not password:
        print("Error: Password is required.", file=sys.stderr)
        sys.exit(1)

    create_admin(email=email, full_name=full_name, password=password)


if __name__ == "__main__":
    main()
