from datetime import datetime
from typing import TYPE_CHECKING, List
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.ticket import Ticket


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    email: Mapped[str] = mapped_column(sa.String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        sa.Enum(UserRole, name="user_role", values_callable=lambda obj: [e.value for e in obj]),
        default=UserRole.REQUESTER,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True, server_default=sa.true(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    requested_tickets: Mapped[List["Ticket"]] = relationship(
        "Ticket",
        back_populates="requester",
        foreign_keys="Ticket.requester_id",
        cascade="all, delete-orphan",
    )
    assigned_tickets: Mapped[List["Ticket"]] = relationship(
        "Ticket",
        back_populates="assignee",
        foreign_keys="Ticket.assignee_id",
    )
