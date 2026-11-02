from datetime import date, datetime, timezone
from typing import Any

STATUS_COLORS: dict[str, str] = {
    "open": "#3182ce",                  # Blue
    "in_progress": "#dd6b20",           # Orange
    "waiting_on_requester": "#805ad5",  # Purple
    "resolved": "#38a169",              # Green
    "closed": "#718096",                # Gray
}


def get_status_color(status: str) -> str:
    """Return hex color for a status, safely defaulting to #718096 for unknown statuses."""
    return STATUS_COLORS.get(str(status).lower(), "#718096")


PRIORITY_COLORS: dict[str, str] = {
    "urgent": "#e53e3e",      # Red
    "high": "#dd6b20",        # Orange
    "medium": "#3182ce",      # Blue
    "low": "#718096",         # Gray
}

CATEGORY_OPTIONS: list[str] = [
    "network",
    "hardware",
    "software",
    "access",
    "email",
    "other",
]


def get_local_timezone() -> Any:
    """Return the machine's local timezone."""
    return datetime.now().astimezone().tzinfo or timezone.utc


def format_datetime(value: Any) -> str:
    """
    Format timestamps into the viewer's local timezone.

    - Naive datetime/timestamps from the API are treated as UTC.
    - Converted to the machine's local timezone (.astimezone()).
    - Formatted as 'Oct 25, 12:27' (%b %d, %H:%M).
    - Returns '-' for None, empty, or unparseable non-string inputs.
    - Gracefully handles strings (ISO 8601 with/without timezone or 'Z') and datetime objects.
    - Handles invalid input without raising exceptions.
    """
    if value is None:
        return "-"

    if isinstance(value, str):
        val_str = value.strip()
        if not val_str or val_str.lower() in ("-", "none", "null"):
            return "-"
        try:
            clean_str = val_str[:-1] + "+00:00" if val_str.endswith("Z") else val_str
            dt = datetime.fromisoformat(clean_str)
        except (ValueError, TypeError):
            try:
                dt = datetime.strptime(val_str, "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                return str(value)
    elif isinstance(value, datetime):
        dt = value
    else:
        return "-"

    # Treat naive values as UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    try:
        local_tz = get_local_timezone()
        local_dt = dt.astimezone(local_tz)
        return local_dt.strftime("%b %d, %H:%M")
    except Exception:
        return str(value)


def format_user_display(
    name: Any = None,
    user_id: Any = None,
    fallback_unassigned: str = "-",
) -> str:
    """
    Format user display string preferring full name, falling back to 'User #<id>', or '-' if none.
    """
    if name is not None and str(name).strip():
        return str(name).strip()
    if user_id is not None and str(user_id).strip():
        return f"User #{user_id}"
    return fallback_unassigned


def format_due_display(
    due_at: Any,
    is_overdue: bool = False,
    sla_paused_at: Any = None,
) -> str:
    """
    Format due display HTML for tickets list table.
    - If sla_paused_at is set: shows 'SLA paused' in waiting_on_requester color (#805ad5), never overdue.
    - If is_overdue is True and sla_paused_at is None: shows '⚠️ <due_at> (OVERDUE)' in red (#e53e3e).
    - Otherwise: shows formatted due date.
    """
    if (
        sla_paused_at is not None
        and str(sla_paused_at).strip()
        and str(sla_paused_at).lower() not in ("none", "null", "-")
    ):
        color = get_status_color("waiting_on_requester")
        return f"<span style='color: {color}; font-weight: bold;'>SLA paused</span>"

    formatted_due = format_datetime(due_at)
    if is_overdue:
        return f"<span style='color: #e53e3e; font-weight: bold;'>⚠️ {formatted_due} (OVERDUE)</span>"
    return f"<span>{formatted_due}</span>"


def get_transition_button_label(from_status: str, to_status: str) -> str:
    """
    Return human-readable button label for an allowed status transition.
    - waiting_on_requester -> in_progress: 'Resume work'
    - in_progress -> waiting_on_requester: 'Pause SLA'
    - * -> resolved: 'Resolve ticket'
    - * -> closed: 'Close ticket'
    - resolved -> in_progress: 'Reopen ticket'
    - open -> in_progress: 'Start work'
    - Default fallback: 'Move to <Status>'
    """
    from_s = str(from_status).lower()
    to_s = str(to_status).lower()

    if from_s == "waiting_on_requester" and to_s == "in_progress":
        return "Resume work"
    if from_s == "in_progress" and to_s == "waiting_on_requester":
        return "Pause SLA"
    if to_s == "resolved":
        return "Resolve ticket"
    if to_s == "closed":
        return "Close ticket"
    if from_s == "resolved" and to_s == "in_progress":
        return "Reopen ticket"
    if from_s == "open" and to_s == "in_progress":
        return "Start work"

    return f"Move to {to_s.replace('_', ' ').title()}"


def format_day_of_week(val: Any) -> str:
    """Return the day of week name (e.g. 'Monday', 'Tuesday') for a date/datetime or ISO string."""
    if val is None:
        return "-"
    if isinstance(val, str):
        val_str = val.strip()
        if not val_str or val_str.lower() in ("none", "null", "-"):
            return "-"
        try:
            val = date.fromisoformat(val_str)
        except Exception:
            try:
                val = datetime.fromisoformat(val_str).date()
            except Exception:
                return "-"
    elif isinstance(val, datetime):
        val = val.date()

    if isinstance(val, date):
        return val.strftime("%A")
    return "-"


def format_similarity(value: Any) -> str:
    """
    Format cosine similarity float (0.0 to 1.0) into a clean percentage string (e.g. 0.87 -> '87%').
    Safely handles None, invalid inputs, and clamps to [0, 100].
    """
    if value is None:
        return "0%"
    try:
        val = float(value)
        pct = int(round(val * 100))
        pct = max(0, min(100, pct))
        return f"{pct}%"
    except (ValueError, TypeError):
        return "0%"


def format_confidence(value: Any) -> str:
    """
    Format confidence float (0.0 to 1.0) into a percentage string (e.g. 0.75 -> '75%').
    Safely handles None, invalid inputs, and clamps to [0, 100].
    """
    return format_similarity(value)


def format_similar_ticket_row(ticket_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Transform a similar ticket dictionary into display row elements.
    Includes formatted similarity percentage, status color, and clean labels.
    """
    if not isinstance(ticket_dict, dict):
        return {}

    status_val = str(ticket_dict.get("status", "open")).lower()
    return {
        "id": ticket_dict.get("id"),
        "title": str(ticket_dict.get("title", "")),
        "status": status_val,
        "status_label": status_val.replace("_", " ").upper(),
        "status_color": get_status_color(status_val),
        "category": str(ticket_dict.get("category", "other")).lower(),
        "priority": str(ticket_dict.get("priority", "medium")).lower(),
        "similarity": float(ticket_dict.get("similarity", 0.0) or 0.0),
        "similarity_pct": format_similarity(ticket_dict.get("similarity")),
    }

