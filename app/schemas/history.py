from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

from app.models.enums import TicketStatus


class StatusHistoryRead(BaseModel):
    """Public schema for reading a ticket status history entry."""
    id: int
    ticket_id: int
    changed_by_id: Optional[int]
    from_status: Optional[TicketStatus]
    to_status: TicketStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
