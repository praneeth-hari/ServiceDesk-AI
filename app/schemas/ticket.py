from app.schemas.common import UTCDateTime
from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models.enums import TicketCategory, TicketPriority, TicketStatus


class TriageSuggestionCreate(BaseModel):
    """AI triage advisory payload captured when a ticket is created."""
    suggested_category: TicketCategory
    suggested_priority: TicketPriority
    method: Literal["knn", "llm-rag"]
    embedder: Optional[str] = None


class TicketCreate(BaseModel):
    """Schema for creating a new ticket."""
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    priority: TicketPriority = TicketPriority.MEDIUM
    category: TicketCategory = TicketCategory.OTHER
    triage_suggestion: Optional[TriageSuggestionCreate] = None


class TicketUpdate(BaseModel):
    """Schema for updating ticket title, description, priority, or category."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, min_length=1)
    priority: Optional[TicketPriority] = None
    category: Optional[TicketCategory] = None


class TicketStatusUpdate(BaseModel):
    """Schema for updating ticket status."""
    status: TicketStatus


class TicketAssign(BaseModel):
    """Schema for assigning a ticket to an agent."""
    assignee_id: int


class TicketRead(BaseModel):
    """Safe schema for reading ticket details, including SLA due date and overdue status."""
    id: int
    title: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    category: TicketCategory
    requester_id: int
    assignee_id: Optional[int]
    requester_name: Optional[str] = None
    assignee_name: Optional[str] = None
    due_at: Optional[UTCDateTime] = None
    sla_paused_at: Optional[UTCDateTime] = None
    resolved_at: Optional[UTCDateTime] = None
    created_at: UTCDateTime
    updated_at: UTCDateTime

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def is_overdue(self) -> bool:
        """
        Computed overdue flag:
        Returns True only when due_at is in the past, ticket is currently open or in_progress,
        and SLA is not currently paused (sla_paused_at is None).
        """
        if self.sla_paused_at is not None:
            return False

        if self.due_at is None:
            return False

        # Ensure due_at is compared timezone-aware in UTC
        due = self.due_at if self.due_at.tzinfo else self.due_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return due < now and self.status in (TicketStatus.OPEN, TicketStatus.IN_PROGRESS)


class PaginatedTickets(BaseModel):
    """Paginated response containing list of tickets and metadata."""
    items: list[TicketRead]
    total: int
    page: int
    page_size: int
