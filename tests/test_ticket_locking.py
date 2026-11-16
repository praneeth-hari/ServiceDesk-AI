"""
Read-check-write ticket changes must lock the ticket row, so two concurrent writers are applied
one after the other. SQLite (used by most tests) ignores row locks, so these tests compile the
statements the services run for MySQL and check that they contain FOR UPDATE on the tickets table.
"""
import pytest
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session

from app.models.enums import TicketCategory, TicketPriority, TicketStatus
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.ticket import TicketAssign, TicketStatusUpdate, TicketUpdate
from app.services import tickets as ticket_service


@pytest.fixture
def ticket(db_session: Session, requester_user: User) -> Ticket:
    t = Ticket(
        title="Locked ticket",
        description="Checks row locking",
        status=TicketStatus.OPEN,
        priority=TicketPriority.MEDIUM,
        category=TicketCategory.OTHER,
        requester_id=requester_user.id,
    )
    db_session.add(t)
    db_session.commit()
    return t


def _ticket_select_sql(monkeypatch: pytest.MonkeyPatch, db: Session, call) -> list[str]:
    """Run `call` and return the MySQL SQL of every SELECT on tickets that it executes."""
    captured: list[str] = []
    original = db.scalars
    # A live connection to MySQL 8 (the version this app targets) turns on "FOR UPDATE OF <table>";
    # an unconnected dialect leaves it off, so switch it on here.
    dialect = mysql.dialect()
    dialect.supports_for_update_of = True

    def spy(statement, *args, **kwargs):
        sql = str(statement.compile(dialect=dialect))
        if "FROM tickets" in sql:
            captured.append(sql)
        return original(statement, *args, **kwargs)

    monkeypatch.setattr(db, "scalars", spy)
    call()
    return captured


def _has_lock(sql: str) -> bool:
    return "FOR UPDATE OF tickets" in sql


def test_status_change_locks_ticket_row(monkeypatch, db_session, agent_user, ticket):
    statements = _ticket_select_sql(
        monkeypatch,
        db_session,
        lambda: ticket_service.update_ticket_status(
            db_session, ticket.id, TicketStatusUpdate(status=TicketStatus.IN_PROGRESS), agent_user
        ),
    )
    assert any(_has_lock(s) for s in statements)


def test_assign_locks_ticket_row(monkeypatch, db_session, agent_user, ticket):
    statements = _ticket_select_sql(
        monkeypatch,
        db_session,
        lambda: ticket_service.assign_ticket(
            db_session, ticket.id, TicketAssign(assignee_id=agent_user.id), agent_user
        ),
    )
    assert any(_has_lock(s) for s in statements)


def test_update_locks_ticket_row(monkeypatch, db_session, admin_user, ticket):
    statements = _ticket_select_sql(
        monkeypatch,
        db_session,
        lambda: ticket_service.update_ticket(
            db_session, ticket.id, TicketUpdate(title="New title"), admin_user
        ),
    )
    assert any(_has_lock(s) for s in statements)


def test_plain_reads_do_not_lock(monkeypatch, db_session, agent_user, ticket):
    statements = _ticket_select_sql(
        monkeypatch,
        db_session,
        lambda: ticket_service.get_ticket_by_id(db_session, ticket.id, agent_user),
    )
    assert statements
    assert not any("FOR UPDATE" in s for s in statements)


def test_lock_covers_only_the_ticket_row_not_joined_users(monkeypatch, db_session, agent_user, ticket):
    statements = _ticket_select_sql(
        monkeypatch,
        db_session,
        lambda: ticket_service.get_ticket_by_id(db_session, ticket.id, agent_user, for_update=True),
    )
    locked = [s for s in statements if _has_lock(s)]
    assert locked
    assert all("FOR UPDATE OF tickets" in s and "OF users" not in s for s in locked)
