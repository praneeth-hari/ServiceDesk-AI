"""create triage_feedback table

Revision ID: 0010_triage_feedback
Revises: 0009_add_resolved_at
Create Date: 2026-11-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0010_triage_feedback"
down_revision: Union[str, None] = "0009_add_resolved_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "triage_feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("embedder", sa.String(length=64), nullable=True),
        sa.Column("suggested_category", sa.String(length=32), nullable=False),
        sa.Column("suggested_priority", sa.String(length=32), nullable=False),
        sa.Column("requester_category", sa.String(length=32), nullable=False),
        sa.Column("requester_priority", sa.String(length=32), nullable=False),
        sa.Column("final_category", sa.String(length=32), nullable=True),
        sa.Column("final_priority", sa.String(length=32), nullable=True),
        sa.Column("final_set_by", sa.Integer(), nullable=True),
        sa.Column("final_set_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["final_set_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_id", name="uq_triage_feedback_ticket_id"),
    )
    op.create_index(
        op.f("ix_triage_feedback_created_at"),
        "triage_feedback",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("triage_feedback")

