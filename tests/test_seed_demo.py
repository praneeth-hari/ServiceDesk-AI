from datetime import datetime, timezone
import zoneinfo
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.core.sla import business_minutes_between, calculate_due_at
from app.models.comment import TicketComment
from app.models.embedding import TicketEmbedding
from app.models.enums import TicketCategory, TicketPriority, TicketStatus, UserRole
from app.models.history import TicketStatusHistory
from app.models.ticket import Ticket
from app.models.user import User
from app.scripts.seed_demo import (
    get_demo_ticket_blueprints,
    main,
    seed_demo,
)
from app.services.holidays import get_holiday_dates
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
    assert summary["tickets_created"] == 36


def test_seed_demo_creates_users_and_roles(db_session: Session):
    """Verify demo users are created with proper credentials and roles."""
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
    assert summary["tickets_created"] == 36

    tickets = db_session.scalars(select(Ticket)).all()
    assert len(tickets) == 36

    # All 6 categories represented
    categories = {t.category for t in tickets}
    assert categories == set(TicketCategory)

    # All 4 priorities represented
    priorities = {t.priority for t in tickets}
    assert priorities == set(TicketPriority)

    # Statuses represented
    statuses = {t.status for t in tickets}
    assert TicketStatus.OPEN in statuses
    assert TicketStatus.IN_PROGRESS in statuses
    assert TicketStatus.WAITING_ON_REQUESTER in statuses
    assert TicketStatus.RESOLVED in statuses
    assert TicketStatus.CLOSED in statuses

    # Overdue unresolved tickets exist
    now = datetime.now(timezone.utc)
    overdue_unresolved = [
        t for t in tickets
        if t.status in (TicketStatus.OPEN, TicketStatus.IN_PROGRESS)
        and (t.due_at.replace(tzinfo=timezone.utc) if t.due_at.tzinfo is None else t.due_at) < now
    ]
    assert len(overdue_unresolved) >= 2

    # Comments: both public and internal comments exist
    comments = db_session.scalars(select(TicketComment)).all()
    assert len(comments) > 0
    assert any(c.is_internal is False for c in comments)
    assert any(c.is_internal is True for c in comments)

    # Status history exists
    history_entries = db_session.scalars(select(TicketStatusHistory)).all()
    assert len(history_entries) > 0


def test_seed_demo_dry_run_makes_no_changes(db_session: Session):
    """Dry-run prints summary table and does not insert any tickets or users."""
    summary = seed_demo(db=db_session, dry_run=True, allow_seed=True)
    assert summary["dry_run"] is True
    assert summary["tickets_planned"] == 36
    assert summary["tickets_created"] == 0

    tickets = db_session.scalars(select(Ticket)).all()
    assert len(tickets) == 0


def test_seed_demo_dry_run_all_states_present_and_robust_to_time():
    """
    Assert that every required state is present in the blueprints:
    On Track, At Risk, Breached, Paused, Resolved within SLA, Resolved late, Closed.
    Verify robustness across:
    - weekday morning
    - weekday evening after 18:00
    - Saturday
    - Sunday
    """
    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    test_scenarios = [
        ("Weekday morning (Wed 10:00 IST)", datetime(2026, 11, 4, 10, 0, tzinfo=tz).astimezone(timezone.utc)),
        ("Weekday evening (Wed 20:30 IST)", datetime(2026, 11, 4, 20, 30, tzinfo=tz).astimezone(timezone.utc)),
        ("Saturday (Sat 14:00 IST)", datetime(2026, 11, 7, 14, 0, tzinfo=tz).astimezone(timezone.utc)),
        ("Sunday (Sun 16:00 IST)", datetime(2026, 11, 8, 16, 0, tzinfo=tz).astimezone(timezone.utc)),
    ]

    expected_required_states = {
        "On Track",
        "At Risk",
        "Breached",
        "Paused",
        "Resolved within SLA",
        "Resolved late",
        "Closed",
    }

    for _label, mock_now in test_scenarios:
        blueprints = get_demo_ticket_blueprints(mock_now, set())
        assert len(blueprints) == 36

        states = {b["expected_state"] for b in blueprints}
        assert states == expected_required_states

        breached_count = sum(1 for b in blueprints if b["expected_state"] == "Breached")
        paused_count = sum(1 for b in blueprints if b["expected_state"] == "Paused")
        at_risk_count = sum(1 for b in blueprints if b["expected_state"] == "At Risk")
        on_track_count = sum(1 for b in blueprints if b["expected_state"] == "On Track")

        assert breached_count >= 2
        assert paused_count >= 2
        assert at_risk_count >= 2
        assert on_track_count >= 3


def test_seed_demo_wipe_tickets_safety_check(db_session: Session):
    """--wipe-tickets without allow_seed/--yes reports what it would delete and aborts."""
    # First seed normally
    seed_demo(db=db_session, allow_seed=True)
    initial_count = len(db_session.scalars(select(Ticket)).all())
    assert initial_count == 36

    # Attempt wipe without confirmation
    result = seed_demo(db=db_session, wipe_tickets=True, allow_seed=False)
    assert result["wiped"] is False
    assert result["tickets_would_delete"] == 36

    # Tickets were not touched
    after_count = len(db_session.scalars(select(Ticket)).all())
    assert after_count == 36


def test_seed_demo_all_states_appear_and_due_at_is_consistent(db_session: Session):
    """
    Verify all required states appear in SQLite DB, due_at matches calculate_due_at,
    2 active tickets are unassigned, and comments/history match workflow.
    """
    summary = seed_demo(db=db_session, allow_seed=True)
    assert summary["tickets_created"] == 36

    tickets = db_session.scalars(select(Ticket)).all()
    assert len(tickets) == 36

    now = datetime.now(timezone.utc)
    holidays = get_holiday_dates(db_session)

    # 1. Check due_at consistency
    for t in tickets:
        created_utc = t.created_at if t.created_at.tzinfo else t.created_at.replace(tzinfo=timezone.utc)
        expected_due = calculate_due_at(t.priority, created_utc, holidays)
        expected_due_utc = expected_due if expected_due.tzinfo else expected_due.replace(tzinfo=timezone.utc)
        ticket_due_utc = t.due_at if t.due_at.tzinfo else t.due_at.replace(tzinfo=timezone.utc)
        assert abs((ticket_due_utc - expected_due_utc).total_seconds()) < 2

    # 2. Active tickets assignment: exactly 2 unassigned
    active_tickets = [
        t for t in tickets
        if t.status in (TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.WAITING_ON_REQUESTER)
    ]
    unassigned_active = [t for t in active_tickets if t.assignee_id is None]
    assert len(unassigned_active) == 2
    for t in unassigned_active:
        assert t.status == TicketStatus.OPEN

    agent = get_user_by_email(db_session, "agent@example.com")
    assigned_active = [t for t in active_tickets if t.assignee_id is not None]
    assert len(assigned_active) == len(active_tickets) - 2
    for t in assigned_active:
        assert t.assignee_id == agent.id
        # Transition from open to in_progress performed by the assigned agent
        history_rows = db_session.scalars(
            select(TicketStatusHistory).where(
                TicketStatusHistory.ticket_id == t.id,
                TicketStatusHistory.from_status == TicketStatus.OPEN,
                TicketStatusHistory.to_status == TicketStatus.IN_PROGRESS,
            )
        ).all()
        assert len(history_rows) == 1
        assert history_rows[0].changed_by_id == agent.id

    # 3. Comments: 1 to 4 on each active ticket
    for t in active_tickets:
        ticket_comments = db_session.scalars(
            select(TicketComment).where(TicketComment.ticket_id == t.id)
        ).all()
        assert 1 <= len(ticket_comments) <= 4

    # 4. Breached, Paused, Resolved within SLA, Resolved late, Closed
    breached = [
        t for t in active_tickets
        if t.status in (TicketStatus.OPEN, TicketStatus.IN_PROGRESS)
        and (t.due_at if t.due_at.tzinfo else t.due_at.replace(tzinfo=timezone.utc)) < now
    ]
    assert len(breached) >= 2

    paused = [
        t for t in tickets
        if t.status == TicketStatus.WAITING_ON_REQUESTER and t.sla_paused_at is not None
    ]
    assert len(paused) >= 2

    resolved_within_sla = [
        t for t in tickets
        if t.status == TicketStatus.RESOLVED
        and t.resolved_at is not None
        and (t.resolved_at if t.resolved_at.tzinfo else t.resolved_at.replace(tzinfo=timezone.utc))
        <= (t.due_at if t.due_at.tzinfo else t.due_at.replace(tzinfo=timezone.utc))
    ]
    assert len(resolved_within_sla) >= 2

    resolved_late = [
        t for t in tickets
        if t.status == TicketStatus.RESOLVED
        and t.resolved_at is not None
        and (t.resolved_at if t.resolved_at.tzinfo else t.resolved_at.replace(tzinfo=timezone.utc))
        > (t.due_at if t.due_at.tzinfo else t.due_at.replace(tzinfo=timezone.utc))
    ]
    assert len(resolved_late) >= 2

    closed = [t for t in tickets if t.status == TicketStatus.CLOSED]
    assert len(closed) >= 1


def test_seed_demo_idempotence_without_wipe(db_session: Session, capsys: pytest.CaptureFixture[str]):
    """Running seed twice WITHOUT --wipe-tickets does not duplicate tickets and prints skip notice."""
    first_run = seed_demo(db=db_session, allow_seed=True)
    assert first_run["tickets_created"] == 36
    assert first_run["tickets_skipped"] == 0
    assert len(db_session.scalars(select(Ticket)).all()) == 36

    second_run = seed_demo(db=db_session, allow_seed=True)
    captured = capsys.readouterr()
    assert "demo tickets already present, nothing added" in captured.out
    assert second_run["tickets_created"] == 0
    assert second_run["tickets_skipped"] == 36
    assert len(db_session.scalars(select(Ticket)).all()) == 36


def test_seed_demo_wipe_tickets_idempotence(db_session: Session):
    """Running seed twice WITH --wipe-tickets --yes wipes and reseeds identical counts."""
    first = seed_demo(db=db_session, wipe_tickets=True, allow_seed=True)
    assert first["tickets_created"] == 36
    first_tickets = len(db_session.scalars(select(Ticket)).all())
    first_comments = len(db_session.scalars(select(TicketComment)).all())
    first_history = len(db_session.scalars(select(TicketStatusHistory)).all())

    second = seed_demo(db=db_session, wipe_tickets=True, allow_seed=True)
    assert second["tickets_created"] == 36
    second_tickets = len(db_session.scalars(select(Ticket)).all())
    second_comments = len(db_session.scalars(select(TicketComment)).all())
    second_history = len(db_session.scalars(select(TicketStatusHistory)).all())

    assert first_tickets == second_tickets == 36
    assert first_comments == second_comments
    assert first_history == second_history


def test_seed_demo_main_cli_success(monkeypatch: pytest.MonkeyPatch, db_session: Session):
    """Test main() CLI execution with --yes flag."""
    monkeypatch.setattr("sys.argv", ["seed_demo", "--yes"])
    monkeypatch.setattr("app.scripts.seed_demo.SessionLocal", lambda: db_session)

    # Should run to completion without error
    main()


def test_seed_demo_creates_ticket_embeddings(db_session: Session):
    """Every seeded ticket must have a corresponding row in ticket_embeddings."""
    seed_demo(db=db_session, allow_seed=True)
    tickets = db_session.scalars(select(Ticket)).all()
    assert len(tickets) == 36

    embeddings = db_session.scalars(select(TicketEmbedding)).all()
    assert len(embeddings) == 36

    ticket_ids = {t.id for t in tickets}
    embedded_ticket_ids = {e.ticket_id for e in embeddings}
    assert ticket_ids == embedded_ticket_ids


def test_seed_demo_wipe_cleans_ticket_embeddings(db_session: Session):
    """Wiping tickets must delete embeddings and leave no orphan rows."""
    seed_demo(db=db_session, allow_seed=True)
    assert len(db_session.scalars(select(TicketEmbedding)).all()) == 36

    # Wipe with --wipe-tickets --yes
    seed_demo(db=db_session, wipe_tickets=True, allow_seed=True)
    # Reseeded tickets
    assert len(db_session.scalars(select(TicketEmbedding)).all()) == 36

    # Verify wiping directly removes them
    db_session.query(TicketEmbedding).delete()
    db_session.commit()
    assert len(db_session.scalars(select(TicketEmbedding)).all()) == 0
