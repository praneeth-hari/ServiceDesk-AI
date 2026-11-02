from datetime import datetime
from typing import TYPE_CHECKING, Optional
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.enums import TicketStatus

if TYPE_CHECKING:
    from app.models.ticket import Ticket
    from app.models.user import User


class TicketStatusHistory(Base):
    __tablename__ = "ticket_status_history"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(
        sa.ForeignKey("tickets.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    changed_by_id: Mapped[Optional[int]] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    from_status: Mapped[Optional[TicketStatus]] = mapped_column(
        sa.Enum(TicketStatus, name="ticket_status", values_callable=lambda obj: [e.value for e in obj]),
        nullable=True,
    )
    to_status: Mapped[TicketStatus] = mapped_column(
        sa.Enum(TicketStatus, name="ticket_status", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="status_history")
    changed_by: Mapped[Optional["User"]] = relationship("User")
