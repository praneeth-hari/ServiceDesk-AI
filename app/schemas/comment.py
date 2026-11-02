from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class CommentCreate(BaseModel):
    """Schema for creating a new comment on a ticket."""
    body: str = Field(..., min_length=1, max_length=2000)
    is_internal: bool = False


class CommentRead(BaseModel):
    """Public schema for reading a ticket comment."""
    id: int
    ticket_id: int
    author_id: int
    body: str
    is_internal: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
