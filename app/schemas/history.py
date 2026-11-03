from app.schemas.common import UTCDateTime
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

from app.models.enums import TicketStatus


class StatusHistoryRead(BaseModel):
    """Public schema for reading a ticket status history entry."""
    id: int
    ticket_id: int
    changed_by_id: Optional[int]
    actor_name: Optional[str] = None
    from_status: Optional[TicketStatus]
    to_status: TicketStatus
    created_at: UTCDateTime

    model_config = ConfigDict(from_attributes=True)
