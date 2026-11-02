"""add status and due_at indexes to tickets

Revision ID: 0004_status_due_at_indexes
Revises: 0003_add_due_at
Create Date: 2026-10-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_status_due_at_indexes"
down_revision: Union[str, None] = "0003_add_due_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(op.f("ix_tickets_status"), "tickets", ["status"], unique=False)
    op.create_index(op.f("ix_tickets_due_at"), "tickets", ["due_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tickets_due_at"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_status"), table_name="tickets")
