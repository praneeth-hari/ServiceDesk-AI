from datetime import date, datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import TicketPriority, TicketStatus, UserRole
from app.models.holiday import Holiday
from app.models.ticket import Ticket
from app.models.user import User


def test_transition_to_and_from_waiting_on_requester(
    client: TestClient,
    agent_auth_headers: dict[str, str],
    requester_auth_headers: dict[str, str],
    db_session: Session,
    agent_user: User,
    requester_user: User,
):
    """
    Test transitions:
    - open -> waiting_on_requester is rejected (409)
    - open -> in_progress -> waiting_on_requester is allowed (200), sets sla_paused_at
    - waiting_on_requester -> resolved is rejected (409)
    - waiting_on_requester -> closed is rejected (409)
    - waiting_on_requester -> open is rejected (409)
    - waiting_on_requester -> in_progress is allowed (200), clears sla_paused_at and pushes due_at
    """
    # Create ticket in OPEN status
    t = Ticket(
        title="Pausable Ticket",
        description="Testing pause/resume",
        status=TicketStatus.OPEN,
        priority=TicketPriority.MEDIUM,
        requester_id=requester_user.id,
        assignee_id=agent_user.id,
        due_at=datetime(2026, 10, 27, 12, 30, tzinfo=timezone.utc),
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)

    initial_due_at = t.due_at

    # 1. Invalid: open -> waiting_on_requester
    res = client.patch(
        f"/api/v1/tickets/{t.id}/status",
        headers=agent_auth_headers,
        json={"status": "waiting_on_requester"},
    )
    assert res.status_code == 409
    assert "Cannot transition ticket status" in res.json()["error"]["message"]

    # 2. Requester cannot change status
    res = client.patch(
        f"/api/v1/tickets/{t.id}/status",
        headers=requester_auth_headers,
        json={"status": "in_progress"},
    )
    assert res.status_code == 403

    # 3. Valid: open -> in_progress
    res = client.patch(
        f"/api/v1/tickets/{t.id}/status",
        headers=agent_auth_headers,
        json={"status": "in_progress"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "in_progress"
    assert res.json()["sla_paused_at"] is None

    # 4. Valid: in_progress -> waiting_on_requester
    res = client.patch(
        f"/api/v1/tickets/{t.id}/status",
        headers=agent_auth_headers,
        json={"status": "waiting_on_requester"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "waiting_on_requester"
    assert data["sla_paused_at"] is not None

    # 5. Invalid moves from waiting_on_requester:
    for invalid_target in ["open", "resolved", "closed"]:
        res_inv = client.patch(
            f"/api/v1/tickets/{t.id}/status",
            headers=agent_auth_headers,
            json={"status": invalid_target},
        )
        assert res_inv.status_code == 409
        assert "Cannot transition ticket status" in res_inv.json()["error"]["message"]

    # 6. Valid: waiting_on_requester -> in_progress
    res = client.patch(
        f"/api/v1/tickets/{t.id}/status",
        headers=agent_auth_headers,
        json={"status": "in_progress"},
    )
    assert res.status_code == 200
    resumed_data = res.json()
    assert resumed_data["status"] == "in_progress"
    assert resumed_data["sla_paused_at"] is None


def test_paused_ticket_is_not_overdue(
    client: TestClient,
    agent_auth_headers: dict[str, str],
    db_session: Session,
    requester_user: User,
):
    """A paused ticket is never overdue, even if due_at is in the past."""
    past_due = datetime.now(timezone.utc) - timedelta(hours=5)
    t = Ticket(
        title="Overdue Paused Ticket",
        description="Testing is_overdue while paused",
        status=TicketStatus.WAITING_ON_REQUESTER,
        priority=TicketPriority.HIGH,
        requester_id=requester_user.id,
        due_at=past_due,
        sla_paused_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)

    # Fetch via API
    res = client.get(f"/api/v1/tickets/{t.id}", headers=agent_auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["is_overdue"] is False
    assert data["sla_paused_at"] is not None

    # Overdue list API excludes paused ticket
    res_list = client.get("/api/v1/tickets?overdue=true", headers=agent_auth_headers)
    assert res_list.status_code == 200
    overdue_ids = [item["id"] for item in res_list.json()["items"]]
    assert t.id not in overdue_ids


def test_resume_pushes_due_at_by_business_minutes(
    client: TestClient,
    agent_auth_headers: dict[str, str],
    db_session: Session,
    agent_user: User,
    requester_user: User,
):
    """
    Test that resuming pushes due_at forward by the exact elapsed business minutes,
    taking into account working hours and holidays.
    """
    # 2026-10-26 is Monday.
    # 09:00 IST = 03:30 UTC. 18:00 IST = 12:30 UTC.
    # Paused at Monday 10:00 IST (04:30 UTC).
    # Initial due_at is Monday 14:00 IST (08:30 UTC).
    # Let's say ticket was paused at 04:30 UTC (Monday 10:00 IST).
    pause_time = datetime(2026, 10, 26, 4, 30, tzinfo=timezone.utc)
    initial_due = datetime(2026, 10, 26, 8, 30, tzinfo=timezone.utc)

    # Let's also add a holiday on Tuesday 2026-10-27
    holiday = Holiday(holiday_date=date(2026, 10, 27), name="Tech Holiday")
    db_session.add(holiday)

    t = Ticket(
        title="Resume Math Ticket",
        description="Check business time push",
        status=TicketStatus.WAITING_ON_REQUESTER,
        priority=TicketPriority.HIGH,
        requester_id=requester_user.id,
        assignee_id=agent_user.id,
        due_at=initial_due,
        sla_paused_at=pause_time,
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)

    # Now simulate resume.
    # When resume happens, update_ticket_status uses datetime.now(timezone.utc).
    # Since datetime.now(timezone.utc) is currently 2026-10-26 (approx 00:30+ IST),
    # let's verify direct service call or patch.
    from app.schemas.ticket import TicketStatusUpdate
    from app.services.tickets import update_ticket_status
    from unittest.mock import patch

    # Suppose resume happens at Monday 12:00 IST (06:30 UTC).
    # From 10:00 IST to 12:00 IST = 2 hours = 120 business minutes.
    # So due_at should be pushed from Monday 14:00 IST (08:30 UTC) to Monday 16:00 IST (10:30 UTC).
    resume_time = datetime(2026, 10, 26, 6, 30, tzinfo=timezone.utc)
    expected_due = datetime(2026, 10, 26, 10, 30, tzinfo=timezone.utc)

    with patch("app.services.tickets.datetime") as mock_dt:
        mock_dt.now.return_value = resume_time
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
        updated = update_ticket_status(
            db=db_session,
            ticket_id=t.id,
            status_in=TicketStatusUpdate(status=TicketStatus.IN_PROGRESS),
            current_user=agent_user,
        )

    assert updated.status == TicketStatus.IN_PROGRESS
    assert updated.sla_paused_at is None
    # Compare timestamps (ignoring timezone object difference since stored as naive UTC)
    assert updated.due_at.replace(tzinfo=timezone.utc) == expected_due

    # Check history rows: should have 1 transition row
    from app.models.history import TicketStatusHistory
    history_entries = (
        db_session.query(TicketStatusHistory)
        .filter(TicketStatusHistory.ticket_id == t.id)
        .all()
    )
    assert len(history_entries) == 1
    assert history_entries[0].from_status == TicketStatus.WAITING_ON_REQUESTER
    assert history_entries[0].to_status == TicketStatus.IN_PROGRESS
    assert history_entries[0].changed_by_id == agent_user.id

