from datetime import date, datetime, timedelta, timezone
import zoneinfo
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.sla import (
    SLA_HOURS_BY_PRIORITY,
    add_business_hours,
    add_business_minutes,
    business_minutes_between,
    calculate_due_at,
)
from app.models.enums import TicketPriority, TicketStatus
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.ticket import TicketCreate
from app.services.tickets import create_ticket


def test_due_at_per_priority(client: TestClient, requester_auth_headers: dict[str, str]):
    """Test that on creation, due_at is calculated using business hours for each priority."""
    for priority_str, expected_hours in SLA_HOURS_BY_PRIORITY.items():
        res = client.post(
            "/api/v1/tickets",
            json={
                "title": f"SLA {priority_str.value} Ticket",
                "description": "Checking SLA calculation",
                "priority": priority_str.value,
            },
            headers=requester_auth_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["due_at"] is not None

        created_dt = datetime.fromisoformat(data["created_at"])
        due_dt = datetime.fromisoformat(data["due_at"])

        # Exact business hours check
        expected_due = add_business_hours(created_dt, expected_hours, holidays=set())
        assert due_dt == expected_due
        assert business_minutes_between(created_dt, due_dt, holidays=set()) == expected_hours * 60


def test_priority_change_recalculates_due_at(
    client: TestClient,
    requester_auth_headers: dict[str, str],
    agent_auth_headers: dict[str, str],
    admin_auth_headers: dict[str, str],
):
    """
    Test that priority change recalculates due_at from created_at while open or in_progress,
    but does NOT change due_at once the ticket is resolved or closed.
    """
    # 1. Create ticket with low priority (72 business hours)
    create_res = client.post(
        "/api/v1/tickets",
        json={"title": "Recalculate SLA", "description": "Desc", "priority": "low"},
        headers=requester_auth_headers,
    )
    ticket_id = create_res.json()["id"]
    created_dt = datetime.fromisoformat(create_res.json()["created_at"])
    initial_due_dt = datetime.fromisoformat(create_res.json()["due_at"])
    assert initial_due_dt == add_business_hours(created_dt, 72, holidays=set())

    # 2. Change priority to high (8h) while OPEN -> due_at recalculates
    patch_open = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        headers=requester_auth_headers,
        json={"priority": "high"},
    )
    assert patch_open.status_code == 200
    new_due_dt = datetime.fromisoformat(patch_open.json()["due_at"])
    assert new_due_dt == add_business_hours(created_dt, 8, holidays=set())

    # 3. Move to IN_PROGRESS
    client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        headers=agent_auth_headers,
        json={"status": "in_progress"},
    )

    # 4. Change priority to urgent (2h) while IN_PROGRESS -> due_at recalculates
    patch_in_progress = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        headers=admin_auth_headers,
        json={"priority": "urgent"},
    )
    assert patch_in_progress.status_code == 200
    urgent_due_dt = datetime.fromisoformat(patch_in_progress.json()["due_at"])
    assert urgent_due_dt == add_business_hours(created_dt, 2, holidays=set())

    # 5. Move to RESOLVED
    client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        headers=agent_auth_headers,
        json={"status": "resolved"},
    )

    # 6. Change priority to low while RESOLVED -> due_at does NOT change
    patch_resolved = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        headers=admin_auth_headers,
        json={"priority": "low"},
    )
    assert patch_resolved.status_code == 200
    resolved_due_dt = datetime.fromisoformat(patch_resolved.json()["due_at"])
    assert resolved_due_dt == urgent_due_dt  # Kept unchanged

    # 7. Move to CLOSED
    client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        headers=agent_auth_headers,
        json={"status": "closed"},
    )

    # 8. Change priority while CLOSED -> due_at does NOT change
    patch_closed = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        headers=admin_auth_headers,
        json={"priority": "medium"},
    )
    assert patch_closed.status_code == 200
    closed_due_dt = datetime.fromisoformat(patch_closed.json()["due_at"])
    assert closed_due_dt == urgent_due_dt  # Kept unchanged


def test_overdue_flag_scenarios(
    client: TestClient,
    db_session: Session,
    requester_user: User,
    requester_auth_headers: dict[str, str],
    agent_auth_headers: dict[str, str],
):
    """
    Test is_overdue flag behavior:
    - False before due_at.
    - True after due_at for open and in_progress.
    - False after due_at for resolved and closed.
    """
    # Case A: Future due_at (not overdue)
    future_ticket_res = client.post(
        "/api/v1/tickets",
        json={"title": "Future ticket", "description": "Desc", "priority": "low"},
        headers=requester_auth_headers,
    )
    assert future_ticket_res.status_code == 201
    assert future_ticket_res.json()["is_overdue"] is False

    # Case B: Create ticket in the past using current_time injection
    past_time = datetime.now(timezone.utc) - timedelta(days=10)
    past_ticket = create_ticket(
        db=db_session,
        ticket_in=TicketCreate(title="Past Ticket", description="Desc", priority=TicketPriority.URGENT),
        current_user=requester_user,
        current_time=past_time,
    )

    # 1. Ticket is OPEN and due_at is in past -> is_overdue is True
    res_open = client.get(f"/api/v1/tickets/{past_ticket.id}", headers=requester_auth_headers)
    assert res_open.status_code == 200
    assert res_open.json()["is_overdue"] is True

    # 2. Ticket moves to IN_PROGRESS and due_at is in past -> is_overdue is True
    client.patch(
        f"/api/v1/tickets/{past_ticket.id}/status",
        headers=agent_auth_headers,
        json={"status": "in_progress"},
    )
    res_in_prog = client.get(f"/api/v1/tickets/{past_ticket.id}", headers=requester_auth_headers)
    assert res_in_prog.status_code == 200
    assert res_in_prog.json()["is_overdue"] is True

    # 3. Ticket moves to RESOLVED and due_at is in past -> is_overdue is False
    client.patch(
        f"/api/v1/tickets/{past_ticket.id}/status",
        headers=agent_auth_headers,
        json={"status": "resolved"},
    )
    res_resolved = client.get(f"/api/v1/tickets/{past_ticket.id}", headers=requester_auth_headers)
    assert res_resolved.status_code == 200
    assert res_resolved.json()["is_overdue"] is False

    # 4. Ticket moves to CLOSED and due_at is in past -> is_overdue is False
    client.patch(
        f"/api/v1/tickets/{past_ticket.id}/status",
        headers=agent_auth_headers,
        json={"status": "closed"},
    )
    res_closed = client.get(f"/api/v1/tickets/{past_ticket.id}", headers=requester_auth_headers)
    assert res_closed.status_code == 200
    assert res_closed.json()["is_overdue"] is False


# ==============================================================================
# Pure Business-Hours Math Unit Tests
# ==============================================================================

def test_add_business_hours_friday_to_monday():
    """Created Friday 17:00 local urgent (2h) -> due Monday 10:00 local."""
    tz = zoneinfo.ZoneInfo(settings.WORK_TIMEZONE)
    # Friday 2026-10-23 17:00 IST
    fri_17 = datetime(2026, 10, 23, 17, 0, tzinfo=tz)
    due_utc = add_business_hours(fri_17.astimezone(timezone.utc), 2, holidays=set())
    due_local = due_utc.astimezone(tz)
    assert due_local == datetime(2026, 10, 26, 10, 0, tzinfo=tz)


def test_add_business_hours_created_saturday():
    """Created Saturday (weekend) -> clock starts Monday 09:00 local."""
    tz = zoneinfo.ZoneInfo(settings.WORK_TIMEZONE)
    sat = datetime(2026, 10, 24, 14, 0, tzinfo=tz)
    due_utc = add_business_hours(sat.astimezone(timezone.utc), 2, holidays=set())
    due_local = due_utc.astimezone(tz)
    assert due_local == datetime(2026, 10, 26, 11, 0, tzinfo=tz)


def test_add_business_hours_created_before_0900():
    """Created on a workday before 09:00 -> clock starts same day at 09:00."""
    tz = zoneinfo.ZoneInfo(settings.WORK_TIMEZONE)
    tue_early = datetime(2026, 10, 27, 7, 30, tzinfo=tz)
    due_utc = add_business_hours(tue_early.astimezone(timezone.utc), 4, holidays=set())
    due_local = due_utc.astimezone(tz)
    assert due_local == datetime(2026, 10, 27, 13, 0, tzinfo=tz)


def test_add_business_hours_created_after_1800():
    """Created on a workday after 18:00 -> clock starts next workday at 09:00."""
    tz = zoneinfo.ZoneInfo(settings.WORK_TIMEZONE)
    wed_late = datetime(2026, 10, 28, 19, 15, tzinfo=tz)
    due_utc = add_business_hours(wed_late.astimezone(timezone.utc), 3, holidays=set())
    due_local = due_utc.astimezone(tz)
    assert due_local == datetime(2026, 10, 29, 12, 0, tzinfo=tz)


def test_add_business_hours_exact_1800_boundary():
    """Result landing exactly at 18:00 stays at 18:00 on that day (does not roll)."""
    tz = zoneinfo.ZoneInfo(settings.WORK_TIMEZONE)
    tue_09 = datetime(2026, 10, 27, 9, 0, tzinfo=tz)
    due_utc = add_business_hours(tue_09.astimezone(timezone.utc), 9, holidays=set())
    due_local = due_utc.astimezone(tz)
    assert due_local == datetime(2026, 10, 27, 18, 0, tzinfo=tz)


def test_add_business_hours_spanning_several_days():
    """A duration spanning several days (e.g. 24 business hours = 9h + 9h + 6h = 3 days)."""
    tz = zoneinfo.ZoneInfo(settings.WORK_TIMEZONE)
    tue_09 = datetime(2026, 10, 27, 9, 0, tzinfo=tz)
    # 24 hours: Tue 9h (to 18:00), Wed 9h (to 18:00), Thu 6h (to 15:00)
    due_utc = add_business_hours(tue_09.astimezone(timezone.utc), 24, holidays=set())
    due_local = due_utc.astimezone(tz)
    assert due_local == datetime(2026, 10, 29, 15, 0, tzinfo=tz)


def test_add_business_hours_with_holidays():
    """Holiday in the middle and holiday on Monday after a weekend."""
    tz = zoneinfo.ZoneInfo(settings.WORK_TIMEZONE)
    fri_17 = datetime(2026, 10, 23, 17, 0, tzinfo=tz)

    # 1. Monday 2026-10-26 is a holiday -> rolls past Monday to Tuesday 10:00
    holidays = {date(2026, 10, 26)}
    due_utc = add_business_hours(fri_17.astimezone(timezone.utc), 2, holidays=holidays)
    assert due_utc.astimezone(tz) == datetime(2026, 10, 27, 10, 0, tzinfo=tz)

    # 2. Both Monday and Tuesday are holidays -> rolls to Wednesday 10:00
    holidays_2 = {date(2026, 10, 26), date(2026, 10, 27)}
    due_utc_2 = add_business_hours(fri_17.astimezone(timezone.utc), 2, holidays=holidays_2)
    assert due_utc_2.astimezone(tz) == datetime(2026, 10, 28, 10, 0, tzinfo=tz)


def test_business_time_utc_kolkata_timezone_conversion():
    """Verify conversion correctness between UTC and Asia/Kolkata (UTC+05:30)."""
    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    # 2026-10-27 09:00 IST is 2026-10-27 03:30 UTC
    tue_utc = datetime(2026, 10, 27, 3, 30, tzinfo=timezone.utc)
    due_utc = add_business_hours(tue_utc, 2, holidays=set())
    # 2 hours later in business hours: 11:00 IST = 05:30 UTC
    assert due_utc == datetime(2026, 10, 27, 5, 30, tzinfo=timezone.utc)
    assert due_utc.astimezone(tz) == datetime(2026, 10, 27, 11, 0, tzinfo=tz)


def test_business_minutes_between_scenarios():
    """Test working minutes inside one day, across weekend, across holiday, zero and negative."""
    tz = zoneinfo.ZoneInfo(settings.WORK_TIMEZONE)

    # Inside one day
    tue_10 = datetime(2026, 10, 27, 10, 0, tzinfo=tz)
    tue_1230 = datetime(2026, 10, 27, 12, 30, tzinfo=tz)
    assert business_minutes_between(tue_10, tue_1230, holidays=set()) == 150

    # Outside work hours on same day
    tue_07 = datetime(2026, 10, 27, 7, 0, tzinfo=tz)
    tue_10 = datetime(2026, 10, 27, 10, 0, tzinfo=tz)
    # Only 09:00 to 10:00 counts = 60 min
    assert business_minutes_between(tue_07, tue_10, holidays=set()) == 60

    # Across weekend: Fri 17:00 to Mon 10:00 (1h Fri + 1h Mon = 120 min)
    fri_17 = datetime(2026, 10, 23, 17, 0, tzinfo=tz)
    mon_10 = datetime(2026, 10, 26, 10, 0, tzinfo=tz)
    assert business_minutes_between(fri_17, mon_10, holidays=set()) == 120

    # Across holiday: Fri 17:00 to Tue 10:00 where Mon is holiday
    tue_10 = datetime(2026, 10, 27, 10, 0, tzinfo=tz)
    assert business_minutes_between(fri_17, tue_10, holidays={date(2026, 10, 26)}) == 120

    # Zero or negative window
    assert business_minutes_between(tue_1230, tue_10, holidays=set()) == 0
    assert business_minutes_between(tue_10, tue_10, holidays=set()) == 0
