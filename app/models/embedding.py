from datetime import datetime
from typing import TYPE_CHECKING, Optional
import numpy as np
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.ticket import Ticket


class TicketEmbedding(Base):
    __tablename__ = "ticket_embeddings"

    ticket_id: Mapped[int] = mapped_column(
        sa.ForeignKey("tickets.id", ondelete="CASCADE"),
        primary_key=True,
    )
    model_name: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    dim: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    vector: Mapped[bytes] = mapped_column(sa.LargeBinary, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="embedding")

    def get_numpy_vector(self) -> np.ndarray:
        """Decode stored bytes into a 1D float32 numpy vector."""
        return np.frombuffer(self.vector, dtype=np.float32)

    @classmethod
    def from_numpy(
        cls,
        ticket_id: int,
        model_name: str,
        vec: np.ndarray,
        updated_at: Optional[datetime] = None,
    ) -> "TicketEmbedding":
        """Construct TicketEmbedding from a numpy array."""
        f32_vec = vec.astype(np.float32)
        return cls(
            ticket_id=ticket_id,
            model_name=model_name,
            dim=int(f32_vec.shape[0]),
            vector=f32_vec.tobytes(),
            updated_at=updated_at or func.now(),
        )
