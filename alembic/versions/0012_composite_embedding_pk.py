"""composite primary key for ticket_embeddings

Revision ID: 0012_composite_embedding_pk
Revises: 0011_llm_triage_log
Create Date: 2026-11-05 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_composite_embedding_pk"
down_revision: Union[str, None] = "0011_llm_triage_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "mysql":
        # In MySQL, ticket_id is a foreign key referencing tickets(id).
        # Dropping and adding primary key must happen in one statement so foreign key stays indexed.
        op.execute(
            "ALTER TABLE ticket_embeddings DROP PRIMARY KEY, ADD PRIMARY KEY (ticket_id, model_name)"
        )
    else:
        # SQLite does not support altering primary keys in-place; batch recreate table.
        with op.batch_alter_table("ticket_embeddings", recreate="always") as batch_op:
            batch_op.create_primary_key("pk_ticket_embeddings", ["ticket_id", "model_name"])


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # Downgrade: keep one row per ticket (prefer hashing-v2) and restore single-column primary key (ticket_id).
    if dialect == "mysql":
        # 1. Delete rows where model_name != 'hashing-v2' if a 'hashing-v2' row exists for that ticket
        op.execute(
            """
            DELETE t1 FROM ticket_embeddings t1
            INNER JOIN ticket_embeddings t2 ON t1.ticket_id = t2.ticket_id
            WHERE t1.model_name != 'hashing-v2' AND t2.model_name = 'hashing-v2'
            """
        )
        # 2. If any ticket has multiple non-hashing-v2 rows, keep the lexicographically first model_name
        op.execute(
            """
            DELETE t1 FROM ticket_embeddings t1
            INNER JOIN ticket_embeddings t2 ON t1.ticket_id = t2.ticket_id
            WHERE t1.model_name > t2.model_name
            """
        )
        op.execute(
            "ALTER TABLE ticket_embeddings DROP PRIMARY KEY, ADD PRIMARY KEY (ticket_id)"
        )
    else:
        # SQLite: prune duplicates preferring hashing-v2
        op.execute(
            """
            DELETE FROM ticket_embeddings
            WHERE model_name != 'hashing-v2'
              AND ticket_id IN (
                  SELECT ticket_id FROM (
                      SELECT ticket_id FROM ticket_embeddings WHERE model_name = 'hashing-v2'
                  ) AS sub
              )
            """
        )
        with op.batch_alter_table("ticket_embeddings", recreate="always") as batch_op:
            batch_op.create_primary_key("pk_ticket_embeddings", ["ticket_id"])

