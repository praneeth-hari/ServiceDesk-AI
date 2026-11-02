"""add category to tickets

Revision ID: 0005_add_category
Revises: 0004_status_due_at_indexes
Create Date: 2026-10-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0005_add_category"
down_revision: Union[str, None] = "0004_status_due_at_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column(
            "category",
            sa.Enum(
                "network",
                "hardware",
                "software",
                "access",
                "email",
                "other",
                name="ticket_category",
            ),
            server_default="other",
            nullable=False,
        ),
    )
    op.create_index(op.f("ix_tickets_category"), "tickets", ["category"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tickets_category"), table_name="tickets")
    op.drop_column("tickets", "category")
