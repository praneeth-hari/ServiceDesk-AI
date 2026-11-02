"""create holidays table

Revision ID: 0006_holidays
Revises: 0005_add_category
Create Date: 2026-10-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0006_holidays"
down_revision: Union[str, None] = "0005_add_category"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "holidays",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_holidays_id"), "holidays", ["id"], unique=False)
    op.create_index(op.f("ix_holidays_holiday_date"), "holidays", ["holiday_date"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_holidays_holiday_date"), table_name="holidays")
    op.drop_index(op.f("ix_holidays_id"), table_name="holidays")
    op.drop_table("holidays")
