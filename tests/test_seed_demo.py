from datetime import datetime, timezone
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.comment import TicketComment
from app.models.enums import TicketCategory, TicketPriority, TicketStatus, UserRole
from app.models.history import TicketStatusHistory
from app.models.ticket import Ticket
from app.models.user import User
from app.scripts.seed_demo import main, seed_demo
from app.services.users import get_user_by_email


def test_seed_demo_refuses_without_guard(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    """Seed script refuses execution if neither ALLOW_DEMO_SEED=1 nor allow_seed=True is set."""
    monkeypatch.delenv("ALLOW_DEMO_SEED", raising=False)

    with pytest.raises(RuntimeError, match="Demo seed refused"):
        seed_demo(db=db_session, allow_seed=False)


def test_seed_demo_main_cli_refuses_without_guard(monkeypatch: pytest.MonkeyPatch):
    """Main CLI exits with non-zero code if --yes flag and ALLOW_DEMO_SEED=1 are absent."""
    monkeypatch.delenv("ALLOW_DEMO_SEED", raising=False)
    monkeypatch.setattr("sys.argv", ["seed_demo"])

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_seed_demo_with_env_var(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    """Seed script runs when ALLOW_DEMO_SEED=1 is set in the environment."""
    monkeypatch.setenv("ALLOW_DEMO_SEED", "1")

    summary = seed_demo(db=db_session)
    assert summary["users_created"] == 3
    assert summary["tickets_created"] == 10


def test_seed_demo_creates_users_and_roles(db_session: Session):
    """Verify that demo users are created with proper credentials and roles."""
    summary = seed_demo(db=db_session, allow_seed=True)
    assert summary["users_created"] == 3

    admin = get_user_by_email(db_session, "admin@example.com")
    assert admin is not None
    assert admin.role == UserRole.ADMIN
    assert admin.full_name == "System Admin"
    assert verify_password("AdminPassword123!", admin.hashed_password)

    agent = get_user_by_email(db_session, "agent@example.com")
    assert agent is not None
    assert agent.role == UserRole.AGENT
    assert agent.full_name == "Asha Agent"
    assert verify_password("AgentPassword123!", agent.hashed_password)

    requester = get_user_by_email(db_session, "requester@example.com")
    assert requester is not None
    assert requester.role == UserRole.REQUESTER
    assert requester.full_name == "Ravi Requester"
    assert verify_password("RequesterPassword123!", requester.hashed_password)


def test_seed_demo_preserves_existing_user_password_updates_role(db_session: Session):
    """If a demo user exists, their password is untouched but role is updated if necessary."""
    # Pre-create user with a custom password and wrong role
    custom_pass = "CustomExistingPass123!"
    existing = User(
        email="agent@example.com",
        full_name="Existing Agent",
        hashed_password=hash_password(custom_pass),
        role=UserRole.REQUESTER,
        is_active=True,
    )
    db_session.add(existing)
    db_session.commit()

    summary = seed_demo(db=db_session, allow_seed=True)
    assert summary["users_existing"] >= 1

    db_session.refresh(existing)
    assert existing.role == UserRole.AGENT
    assert verify_password(custom_pass, existing.hashed_password)
    assert not verify_password("AgentPassword123!", existing.hashed_password)


def test_seed_demo_tickets_categories_priorities_and_workflow(db_session: Session):
    """Verify tickets cover all categories, priorities, statuses, comments, and overdue flags."""
    summary = seed_demo(db=db_session, allow_seed=True)
    assert summary["tickets_created"] == 10

    tickets = db_session.scalars(select(Ticket)).all()
    assert len(tickets) == 10

    # All 6 categories represented
    categories = {t.category for t in tickets}
    expected_categories = set(TicketCategory)
    assert categories == expected_categories

    # All 4 priorities represented
    priorities = {t.priority for t in tickets}
    expected_priorities = set(TicketPriority)
    assert priorities == expected_priorities

    # Statuses represented
    statuses = {t.status for t in tickets}
    assert TicketStatus.OPEN in statuses
    assert TicketStatus.IN_PROGRESS in statuses
    assert TicketStatus.WAITING_ON_REQUESTER in statuses
    assert TicketStatus.RESOLVED in statuses
    assert TicketStatus.CLOSED in statuses

    # Overdue tickets check: at least 2 or 3 unresolved tickets overdue
    now = datetime.now(timezone.utc)
    overdue_unresolved = [
        t for t in tickets
        if t.status in (TicketStatus.OPEN, TicketStatus.IN_PROGRESS)
        and (t.due_at.replace(tzinfo=timezone.utc) if t.due_at.tzinfo is None else t.due_at) < now
    ]
    assert len(overdue_unresolved) in (2, 3)

    # Comments: both public and internal comments exist
    comments = db_session.scalars(select(TicketComment)).all()
    assert len(comments) > 0
    assert any(c.is_internal is False for c in comments)
    assert any(c.is_internal is True for c in comments)

    # Status history exists
    history_entries = db_session.scalars(select(TicketStatusHistory)).all()
    assert len(history_entries) > 0


def test_seed_demo_idempotence(db_session: Session):
    """Second run must create 0 new tickets and skip all existing demo tickets."""
    first_run = seed_demo(db=db_session, allow_seed=True)
    assert first_run["tickets_created"] == 10
    assert first_run["tickets_skipped"] == 0
    assert first_run["users_created"] == 3

    second_run = seed_demo(db=db_session, allow_seed=True)
    assert second_run["tickets_created"] == 0
    assert second_run["tickets_skipped"] == 10
    assert second_run["users_created"] == 0
    assert second_run["users_existing"] == 3

    # Total ticket count remains 10
    ticket_count = len(db_session.scalars(select(Ticket)).all())
    assert ticket_count == 10


def test_seed_demo_main_cli_success(monkeypatch: pytest.MonkeyPatch, db_session: Session):
    """Test main() CLI execution with --yes flag."""
    monkeypatch.setattr("sys.argv", ["seed_demo", "--yes"])
    # Intercept SessionLocal to return db_session
    monkeypatch.setattr("app.scripts.seed_demo.SessionLocal", lambda: db_session)

    # Should run to completion without error
    main()
