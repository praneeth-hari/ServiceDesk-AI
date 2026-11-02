"""add waiting_on_requester status and sla_paused_at column

Revision ID: 0007_pausable_sla
Revises: 0006_holidays
Create Date: 2026-10-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0007_pausable_sla"
down_revision: Union[str, None] = "0006_holidays"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    # 1. Update ENUM definitions on MySQL to include 'waiting_on_requester'
    if dialect_name == "mysql":
        op.execute(
            "ALTER TABLE tickets MODIFY COLUMN status "
            "ENUM('open', 'in_progress', 'waiting_on_requester', 'resolved', 'closed') NOT NULL"
        )
        op.execute(
            "ALTER TABLE ticket_status_history MODIFY COLUMN from_status "
            "ENUM('open', 'in_progress', 'waiting_on_requester', 'resolved', 'closed') NULL"
        )
        op.execute(
            "ALTER TABLE ticket_status_history MODIFY COLUMN to_status "
            "ENUM('open', 'in_progress', 'waiting_on_requester', 'resolved', 'closed') NOT NULL"
        )

    # 2. Add sla_paused_at column to tickets
    op.add_column(
        "tickets",
        sa.Column("sla_paused_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    # 1. Convert any rows with waiting_on_requester back to in_progress before removing enum value
    op.execute("UPDATE tickets SET status = 'in_progress' WHERE status = 'waiting_on_requester'")
    op.execute(
        "UPDATE ticket_status_history SET from_status = 'in_progress' WHERE from_status = 'waiting_on_requester'"
    )
    op.execute(
        "UPDATE ticket_status_history SET to_status = 'in_progress' WHERE to_status = 'waiting_on_requester'"
    )

    # 2. Drop sla_paused_at column
    op.drop_column("tickets", "sla_paused_at")

    # 3. Revert ENUM on MySQL back to original 4 statuses
    if dialect_name == "mysql":
        op.execute(
            "ALTER TABLE tickets MODIFY COLUMN status "
            "ENUM('open', 'in_progress', 'resolved', 'closed') NOT NULL"
        )
        op.execute(
            "ALTER TABLE ticket_status_history MODIFY COLUMN from_status "
            "ENUM('open', 'in_progress', 'resolved', 'closed') NULL"
        )
        op.execute(
            "ALTER TABLE ticket_status_history MODIFY COLUMN to_status "
            "ENUM('open', 'in_progress', 'resolved', 'closed') NOT NULL"
        )
