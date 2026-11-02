"""create comments and status history tables

Revision ID: 0002_comments_history
Revises: 0001_initial
Create Date: 2026-10-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002_comments_history"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create ticket_comments table
    op.create_table(
        "ticket_comments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_internal", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ticket_comments_id"), "ticket_comments", ["id"], unique=False)
    op.create_index(op.f("ix_ticket_comments_ticket_id"), "ticket_comments", ["ticket_id"], unique=False)

    # 2. Create ticket_status_history table
    op.create_table(
        "ticket_status_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("changed_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "from_status",
            sa.Enum("open", "in_progress", "resolved", "closed", name="ticket_status"),
            nullable=True,
        ),
        sa.Column(
            "to_status",
            sa.Enum("open", "in_progress", "resolved", "closed", name="ticket_status"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["changed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ticket_status_history_id"), "ticket_status_history", ["id"], unique=False)
    op.create_index(op.f("ix_ticket_status_history_ticket_id"), "ticket_status_history", ["ticket_id"], unique=False)


def downgrade() -> None:
    # Drop tables in reverse dependency order (child tables first)
    # Dropping the table automatically removes all associated indexes without triggering MySQL error 1553
    op.drop_table("ticket_status_history")
    op.drop_table("ticket_comments")

