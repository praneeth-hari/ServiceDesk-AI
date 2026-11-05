from datetime import datetime, timezone
from typing import Optional
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class LLMTriageLog(Base):
    """
    Telemetry log for LLM triage requests.
    Stores operational timing and fallback reasons only.
    Contains NO ticket text, titles, descriptions, user IDs, or emails.
    """
    __tablename__ = "llm_triage_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    method: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    latency_ms: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    fallback_reason: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True)
