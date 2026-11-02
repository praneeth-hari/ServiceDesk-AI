"""create ticket_embeddings table

Revision ID: 0008_ticket_embeddings
Revises: 0007_pausable_sla
Create Date: 2026-10-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0008_ticket_embeddings"
down_revision: Union[str, None] = "0007_pausable_sla"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ticket_embeddings",
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("vector", sa.LargeBinary(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("ticket_id"),
    )
    op.create_index(
        op.f("ix_ticket_embeddings_model_name"),
        "ticket_embeddings",
        ["model_name"],
        unique=False,
    )


def downgrade() -> None:
    # Dropping the table directly avoids dropping foreign key backing indexes in MySQL
    op.drop_table("ticket_embeddings")
