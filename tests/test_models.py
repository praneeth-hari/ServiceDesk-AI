from sqlalchemy.orm import Session

from app.models.enums import TicketPriority, TicketStatus, UserRole
from app.models.ticket import Ticket
from app.models.user import User


def test_create_user(db_session: Session):
    """Test creating a User with default role and active status."""
    user = User(
        email="testuser@example.com",
        full_name="Test User",
        hashed_password="hashed_secret_password",
    )
    db_session.add(user)
    db_session.flush()

    assert user.id is not None
    assert user.email == "testuser@example.com"
    assert user.full_name == "Test User"
    assert user.role == UserRole.REQUESTER
    assert user.is_active is True
    assert user.created_at is not None


def test_create_ticket_with_relationships(db_session: Session):
    """Test creating a Ticket linked to a requester and assignee."""
    requester = User(
        email="requester@example.com",
        full_name="Requester User",
        hashed_password="secret_password",
        role=UserRole.REQUESTER,
    )
    agent = User(
        email="agent@example.com",
        full_name="Support Agent",
        hashed_password="secret_password",
        role=UserRole.AGENT,
    )
    db_session.add_all([requester, agent])
    db_session.flush()

    ticket = Ticket(
        title="Printer not working",
        description="Printer on 2nd floor gives paper jam error.",
        priority=TicketPriority.HIGH,
        requester_id=requester.id,
        assignee_id=agent.id,
    )
    db_session.add(ticket)
    db_session.flush()

    assert ticket.id is not None
    assert ticket.status == TicketStatus.OPEN
    assert ticket.priority == TicketPriority.HIGH
    assert ticket.requester.full_name == "Requester User"
    assert ticket.assignee.full_name == "Support Agent"
    assert len(requester.requested_tickets) == 1
    assert len(agent.assigned_tickets) == 1
    assert requester.requested_tickets[0].id == ticket.id
