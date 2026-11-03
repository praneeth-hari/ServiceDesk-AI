from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.schemas.common import serialize_utc_datetime
from app.models.user import User


def test_serialize_utc_datetime_helper():
    """Test helper with naive, UTC-aware, and non-UTC aware datetime values."""
    # 1. Naive datetime: assumed to be UTC
    naive_dt = datetime(2026, 10, 23, 12, 10, 0)
    assert serialize_utc_datetime(naive_dt) == "2026-10-23T12:10:00Z"

    # 2. UTC-aware datetime: serialized with Z
    utc_dt = datetime(2026, 10, 23, 12, 10, 0, tzinfo=timezone.utc)
    assert serialize_utc_datetime(utc_dt) == "2026-10-23T12:10:00Z"

    # 3. Non-UTC aware datetime: converted to UTC first
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    ist_dt = datetime(2026, 10, 23, 17, 40, 0, tzinfo=ist_tz)
    assert serialize_utc_datetime(ist_dt) == "2026-10-23T12:10:00Z"

    # 4. None preserves None
    assert serialize_utc_datetime(None) is None


def test_api_datetime_fields_have_trailing_z(
    client: TestClient,
    requester_user: User,
    requester_auth_headers: dict[str, str],
    agent_auth_headers: dict[str, str],
    admin_auth_headers: dict[str, str],
):
    """
    Test real API responses asserting that datetime fields end with 'Z':
    - ticket (created_at, due_at, updated_at, and resolved_at when set)
    - comment (created_at)
    - status history entry (created_at)
    - holiday (created_at)
    """
    # 1. Create a ticket -> check created_at, updated_at, due_at end with 'Z'
    ticket_payload = {
        "title": "UTC Serialization Test Ticket",
        "description": "Checking UTC ISO timestamps with trailing Z",
        "priority": "high",
        "category": "software",
    }
    res = client.post("/api/v1/tickets", json=ticket_payload, headers=requester_auth_headers)
    assert res.status_code == 201
    ticket_data = res.json()
    ticket_id = ticket_data["id"]

    assert ticket_data["created_at"].endswith("Z")
    assert ticket_data["updated_at"].endswith("Z")
    assert ticket_data["due_at"] is not None
    assert ticket_data["due_at"].endswith("Z")
    assert ticket_data["resolved_at"] is None

    # Move ticket to in_progress then resolved -> check resolved_at ends with 'Z'
    res_ip = client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        json={"status": "in_progress"},
        headers=agent_auth_headers,
    )
    assert res_ip.status_code == 200

    res_res = client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        json={"status": "resolved"},
        headers=agent_auth_headers,
    )
    assert res_res.status_code == 200
    resolved_data = res_res.json()
    assert resolved_data["resolved_at"] is not None
    assert resolved_data["resolved_at"].endswith("Z")
    assert resolved_data["updated_at"].endswith("Z")

    # 2. Add a comment -> check created_at ends with 'Z'
    comment_res = client.post(
        f"/api/v1/tickets/{ticket_id}/comments",
        json={"body": "Test comment with UTC timestamp", "is_internal": False},
        headers=requester_auth_headers,
    )
    assert comment_res.status_code == 201
    comment_data = comment_res.json()
    assert comment_data["created_at"].endswith("Z")

    # 3. Retrieve status history -> check each entry's created_at ends with 'Z'
    history_res = client.get(
        f"/api/v1/tickets/{ticket_id}/history",
        headers=agent_auth_headers,
    )
    assert history_res.status_code == 200
    history_data = history_res.json()
    assert len(history_data) >= 2  # open -> in_progress, in_progress -> resolved
    for entry in history_data:
        assert entry["created_at"].endswith("Z")

    # 4. Create a holiday -> check created_at ends with 'Z', holiday_date is YYYY-MM-DD
    holiday_res = client.post(
        "/api/v1/holidays",
        json={"name": "UTC Test Holiday", "holiday_date": "2026-12-25"},
        headers=admin_auth_headers,
    )
    assert holiday_res.status_code == 201
    holiday_data = holiday_res.json()
    assert holiday_data["created_at"].endswith("Z")
    assert holiday_data["holiday_date"] == "2026-12-25"  # Date remains plain date

