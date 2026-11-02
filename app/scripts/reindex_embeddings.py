"""
Rebuild all ticket embeddings using the active embedder.

Usage:
    python -m app.scripts.reindex_embeddings
"""
import logging
import sys
import sqlalchemy as sa

from app.ai.embedder import get_embedder
from app.db.session import SessionLocal
from app.models.ticket import Ticket
from app.services.triage import sync_ticket_embedding

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reindex_embeddings")


def reindex_embeddings() -> int:
    embedder = get_embedder()
    print(
        f"Reindexing embeddings for all tickets using active embedder '{embedder.name}' "
        f"(dim={embedder.dim})..."
    )

    with SessionLocal() as db:
        tickets = db.scalars(sa.select(Ticket).order_by(Ticket.id.asc())).all()
        total = len(tickets)
        processed = 0
        errors = 0

        for ticket in tickets:
            try:
                sync_ticket_embedding(db, ticket, embedder=embedder)
                processed += 1
            except Exception as exc:
                errors += 1
                logger.error("Failed to reindex ticket id=%s: %s", ticket.id, exc)

        db.commit()

    print(
        f"Reindexing completed: {processed}/{total} tickets processed successfully "
        f"({errors} errors) with model '{embedder.name}'."
    )
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(reindex_embeddings())
