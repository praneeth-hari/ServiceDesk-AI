from datetime import datetime, timedelta, timezone
import pytest

from dashboard.formatting import (
    CATEGORY_OPTIONS,
    PRIORITY_COLORS,
    STATUS_COLORS,
    format_datetime,
)


@pytest.fixture
def deterministic_timezone(monkeypatch):
    """Pin get_local_timezone to a fixed UTC+2 timezone (e.g. EET / UTC+02:00)."""
    fixed_tz = timezone(timedelta(hours=2))
    monkeypatch.setattr("dashboard.formatting.get_local_timezone", lambda: fixed_tz)
    return fixed_tz


def test_format_datetime_none():
    """Test None and empty inputs return '-'."""
    assert format_datetime(None) == "-"
    assert format_datetime("") == "-"
    assert format_datetime("   ") == "-"
    assert format_datetime("None") == "-"
    assert format_datetime("null") == "-"


def test_format_datetime_naive_utc_string(deterministic_timezone):
    """
    Test naive UTC string from API is treated as UTC and converted to local timezone.
    Input: 10:27 UTC -> UTC+2: 12:27.
    """
    res = format_datetime("2026-10-25T10:27:00")
    assert res == "Oct 25, 12:27"


def test_format_datetime_timezone_aware_string(deterministic_timezone):
    """
    Test timezone-aware strings (trailing Z or +00:00).
    Input: 10:27 UTC -> UTC+2: 12:27.
    """
    res_z = format_datetime("2026-10-25T10:27:00Z")
    assert res_z == "Oct 25, 12:27"

    res_offset = format_datetime("2026-10-25T10:27:00+00:00")
    assert res_offset == "Oct 25, 12:27"


def test_format_datetime_datetime_object(deterministic_timezone):
    """Test datetime objects (naive and timezone-aware)."""
    # Naive datetime: treated as UTC
    dt_naive = datetime(2026, 10, 25, 10, 27, 0)
    assert format_datetime(dt_naive) == "Oct 25, 12:27"

    # Aware datetime in UTC
    dt_aware = datetime(2026, 10, 25, 10, 27, 0, tzinfo=timezone.utc)
    assert format_datetime(dt_aware) == "Oct 25, 12:27"


def test_format_datetime_invalid_input():
    """Test invalid input does not crash and returns graceful string or '-'."""
    assert format_datetime("invalid-timestamp-string") == "invalid-timestamp-string"
    assert format_datetime(12345) == "-"
    assert format_datetime([]) == "-"


def test_color_and_category_tokens():
    """Test display colors and category constants."""
    from dashboard.formatting import get_status_color

    for s in ("open", "in_progress", "waiting_on_requester", "resolved", "closed"):
        assert s in STATUS_COLORS
        assert STATUS_COLORS[s].startswith("#")
        assert get_status_color(s) == STATUS_COLORS[s]

    # Safe fallback for unknown status
    assert get_status_color("non_existent_status") == "#718096"

    for p in ("low", "medium", "high", "urgent"):
        assert p in PRIORITY_COLORS
        assert PRIORITY_COLORS[p].startswith("#")

    assert set(CATEGORY_OPTIONS) == {"network", "hardware", "software", "access", "email", "other"}


def test_format_user_display():
    """Test format_user_display name preference, ID fallback, and '-' fallback."""
    from dashboard.formatting import format_user_display

    # Prefers name when provided
    assert format_user_display("Asha Agent", 2) == "Asha Agent"
    assert format_user_display("Ravi Requester", 3) == "Ravi Requester"
    assert format_user_display("  Priya Patel  ", 4) == "Priya Patel"

    # Falls back to User #<id> when name is None or blank
    assert format_user_display(None, 5) == "User #5"
    assert format_user_display("", 5) == "User #5"
    assert format_user_display("   ", 5) == "User #5"

    # Falls back to '-' when both are absent or empty
    assert format_user_display(None, None) == "-"
    assert format_user_display("", None) == "-"
    assert format_user_display(None, "") == "-"

    # Custom fallback parameter
    assert format_user_display(None, None, fallback_unassigned="Unassigned") == "Unassigned"


def test_format_due_display(deterministic_timezone):
    """
    Test format_due_display helper:
    - If sla_paused_at is set: returns 'SLA paused' in purple (#805ad5), never overdue.
    - If is_overdue is True and not paused: returns red OVERDUE display.
    - Otherwise: returns regular formatted due date.
    """
    from dashboard.formatting import format_due_display

    due_str = "2026-10-25T10:27:00"

    # 1. Paused ticket (even if is_overdue=True) MUST show 'SLA paused' in waiting colour and NEVER overdue
    res_paused = format_due_display(
        due_at=due_str,
        is_overdue=True,
        sla_paused_at="2026-10-25T08:00:00",
    )
    assert "SLA paused" in res_paused
    assert "#805ad5" in res_paused
    assert "OVERDUE" not in res_paused

    # 2. Overdue ticket without pause
    res_overdue = format_due_display(
        due_at=due_str,
        is_overdue=True,
        sla_paused_at=None,
    )
    assert "OVERDUE" in res_overdue
    assert "#e53e3e" in res_overdue
    assert "Oct 25, 12:27" in res_overdue

    # 3. Regular on-time ticket
    res_regular = format_due_display(
        due_at=due_str,
        is_overdue=False,
        sla_paused_at=None,
    )
    assert "Oct 25, 12:27" in res_regular
    assert "OVERDUE" not in res_regular


def test_get_transition_button_label():
    """Test get_transition_button_label maps states to user-friendly action labels."""
    from dashboard.formatting import get_transition_button_label

    assert get_transition_button_label("waiting_on_requester", "in_progress") == "Resume work"
    assert get_transition_button_label("in_progress", "waiting_on_requester") == "Pause SLA"
    assert get_transition_button_label("in_progress", "resolved") == "Resolve ticket"
    assert get_transition_button_label("open", "in_progress") == "Start work"
    assert get_transition_button_label("resolved", "closed") == "Close ticket"
    assert get_transition_button_label("resolved", "in_progress") == "Reopen ticket"

    # Fallback formatting
    assert get_transition_button_label("custom", "in_review") == "Move to In Review"


def test_format_day_of_week():
    """Test format_day_of_week computes weekday from date, datetime, or ISO string."""
    from datetime import date
    from dashboard.formatting import format_day_of_week

    # Monday: 2026-10-26
    assert format_day_of_week("2026-10-26") == "Monday"
    assert format_day_of_week(date(2026, 10, 26)) == "Monday"
    assert format_day_of_week(datetime(2026, 10, 26, 14, 30)) == "Monday"

    # Friday: 2026-10-30
    assert format_day_of_week("2026-10-30") == "Friday"

    # Invalid / empty
    assert format_day_of_week(None) == "-"
    assert format_day_of_week("") == "-"
    assert format_day_of_week("not-a-date") == "-"
    assert format_day_of_week(12345) == "-"


def test_format_similarity_and_confidence():
    """Test format_similarity and format_confidence for various values."""
    from dashboard.formatting import format_confidence, format_similarity

    assert format_similarity(0.8732) == "87%"
    assert format_similarity(0.87) == "87%"
    assert format_similarity(1.0) == "100%"
    assert format_similarity(0.0) == "0%"
    assert format_similarity(None) == "0%"
    assert format_similarity("not-a-number") == "0%"
    assert format_similarity(-0.5) == "0%"
    assert format_similarity(1.5) == "100%"

    assert format_confidence(0.75) == "75%"
    assert format_confidence(None) == "0%"


def test_format_similar_ticket_row():
    """Test format_similar_ticket_row transforms API ticket dict into display elements."""
    from dashboard.formatting import format_similar_ticket_row, get_status_color

    ticket_data = {
        "id": 42,
        "title": "VPN gateway timeout error",
        "status": "in_progress",
        "category": "network",
        "priority": "high",
        "similarity": 0.884,
    }
    row = format_similar_ticket_row(ticket_data)
    assert row["id"] == 42
    assert row["title"] == "VPN gateway timeout error"
    assert row["status"] == "in_progress"
    assert row["status_label"] == "IN PROGRESS"
    assert row["status_color"] == get_status_color("in_progress")
    assert row["category"] == "network"
    assert row["priority"] == "high"
    assert row["similarity_pct"] == "88%"

    # Non-dict input
    assert format_similar_ticket_row(None) == {}


