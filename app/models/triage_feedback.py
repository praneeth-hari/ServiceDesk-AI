from datetime import datetime
from typing import TYPE_CHECKING, Optional
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.ticket import Ticket
    from app.models.user import User


class TriageFeedback(Base):
    __tablename__ = "triage_feedback"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(
        sa.ForeignKey("tickets.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    method: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    embedder: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True)
    suggested_category: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    suggested_priority: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    requester_category: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    requester_priority: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    final_category: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True)
    final_priority: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True)
    final_set_by: Mapped[Optional[int]] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    final_set_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="triage_feedback")
    reviewer: Mapped[Optional["User"]] = relationship("User")

