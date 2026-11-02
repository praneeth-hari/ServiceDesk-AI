from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import TicketCategory, TicketPriority, TicketStatus


class SimilarTicket(BaseModel):
    """Summary of a similar ticket with its calculated cosine similarity."""
    id: int
    title: str
    status: TicketStatus
    category: TicketCategory
    priority: TicketPriority
    similarity: float

    model_config = ConfigDict(from_attributes=True)


class TriageSuggestRequest(BaseModel):
    """Request payload for AI triage suggestions."""
    title: str = Field(..., min_length=1, max_length=255, description="Ticket title")
    description: str = Field(..., min_length=1, description="Ticket problem description")


class TriageSuggestResponse(BaseModel):
    """Advisory category/priority suggestion and duplicate detection result."""
    suggested_category: Optional[TicketCategory] = None
    suggested_priority: Optional[TicketPriority] = None
    confidence: float = 0.0
    evidence: list[SimilarTicket] = Field(default_factory=list)
    possible_duplicates: list[SimilarTicket] = Field(default_factory=list)
    embedder: str
