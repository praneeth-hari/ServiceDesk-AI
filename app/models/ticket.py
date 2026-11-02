from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.enums import TicketCategory, TicketPriority, TicketStatus

if TYPE_CHECKING:
    from app.models.comment import TicketComment
    from app.models.embedding import TicketEmbedding
    from app.models.history import TicketStatusHistory
    from app.models.user import User


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    title: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    description: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[TicketStatus] = mapped_column(
        sa.Enum(TicketStatus, name="ticket_status", values_callable=lambda obj: [e.value for e in obj]),
        default=TicketStatus.OPEN,
        nullable=False,
        index=True,
    )
    priority: Mapped[TicketPriority] = mapped_column(
        sa.Enum(TicketPriority, name="ticket_priority", values_callable=lambda obj: [e.value for e in obj]),
        default=TicketPriority.MEDIUM,
        nullable=False,
    )
    category: Mapped[TicketCategory] = mapped_column(
        sa.Enum(TicketCategory, name="ticket_category", values_callable=lambda obj: [e.value for e in obj]),
        default=TicketCategory.OTHER,
        server_default=sa.text("'other'"),
        nullable=False,
        index=True,
    )
    requester_id: Mapped[int] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    assignee_id: Mapped[Optional[int]] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    due_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    sla_paused_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    requester: Mapped["User"] = relationship(
        "User",
        foreign_keys=[requester_id],
        back_populates="requested_tickets",
    )
    assignee: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[assignee_id],
        back_populates="assigned_tickets",
    )
    comments: Mapped[List["TicketComment"]] = relationship(
        "TicketComment",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="TicketComment.created_at, TicketComment.id",
    )
    status_history: Mapped[List["TicketStatusHistory"]] = relationship(
        "TicketStatusHistory",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="TicketStatusHistory.created_at, TicketStatusHistory.id",
    )
    embedding: Mapped[Optional["TicketEmbedding"]] = relationship(
        "TicketEmbedding",
        back_populates="ticket",
        cascade="all, delete-orphan",
        uselist=False,
    )

    @property
    def requester_name(self) -> Optional[str]:
        """Return the full name of the ticket requester, or None if unattached."""
        return self.requester.full_name if self.requester else None

    @property
    def assignee_name(self) -> Optional[str]:
        """Return the full name of the assigned agent, or None if unassigned."""
        return self.assignee.full_name if self.assignee else None

