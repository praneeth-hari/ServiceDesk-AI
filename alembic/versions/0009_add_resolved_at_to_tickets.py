"""add resolved_at column to tickets and backfill from status history

Revision ID: 0009_add_resolved_at
Revises: 0008_ticket_embeddings
Create Date: 2026-11-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0009_add_resolved_at"
down_revision: Union[str, None] = "0008_ticket_embeddings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add nullable resolved_at column to tickets
    op.add_column(
        "tickets",
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 2. Backfill existing resolved and closed rows from the latest 'resolved' status history row,
    # falling back to updated_at. Works on both MySQL 8 and SQLite.
    op.execute(
        """
        UPDATE tickets
        SET resolved_at = COALESCE(
            (
                SELECT MAX(h.created_at)
                FROM ticket_status_history h
                WHERE h.ticket_id = tickets.id AND h.to_status = 'resolved'
            ),
            tickets.updated_at
        )
        WHERE tickets.status IN ('resolved', 'closed')
        """
    )


def downgrade() -> None:
    op.drop_column("tickets", "resolved_at")

