from datetime import datetime, timezone
from typing import Annotated, Any
from pydantic import PlainSerializer


def serialize_utc_datetime(v: Any) -> str | None:
    """
    Serialize a datetime to an ISO 8601 string with trailing 'Z' (UTC).
    - If None, returns None.
    - If already a string, returned as-is.
    - If naive, treated as UTC.
    - If timezone-aware, converted to UTC first.
    """
    if v is None:
        return None
    if isinstance(v, str):
        return v
    if not isinstance(v, datetime):
        raise TypeError(f"Expected datetime, got {type(v).__name__}")
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    else:
        v = v.astimezone(timezone.utc)
    return v.isoformat().replace("+00:00", "Z")


UTCDateTime = Annotated[
    datetime,
    PlainSerializer(serialize_utc_datetime, return_type=str),
]

