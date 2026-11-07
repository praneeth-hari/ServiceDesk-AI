"""
Rebuild ticket embeddings for the selected embedder(s).

Usage:
    python -m app.scripts.reindex_embeddings [--embedder hashing|nomic|all] [--missing-only]
"""
import argparse
from datetime import datetime, timezone
import logging
import sys
from typing import Callable, Sequence
import numpy as np
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.ai.embedder import Embedder, OllamaEmbedder, get_embedder, get_text_to_embed
from app.db.session import SessionLocal
from app.models.embedding import TicketEmbedding
from app.models.ticket import Ticket

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reindex_embeddings")

BATCH_SIZE = 32


def parse_args(args: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild ticket embeddings.")
    parser.add_argument(
        "--embedder",
        choices=["hashing", "nomic", "all"],
        default="all",
        help="Embedder to index: 'hashing', 'nomic', or 'all' (default: all)",
    )
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Only reindex tickets missing an embedding for the selected embedder(s)",
    )
    return parser.parse_args(args)


def reindex_embeddings(
    args: Sequence[str] | None = None,
    session_factory: Callable[[], Session] | None = None,
) -> int:
    eff_args = list(args) if args is not None else []
    parsed = parse_args(eff_args)
    embedder_choice = parsed.embedder
    missing_only = parsed.missing_only

    target_embedder_names: list[str] = []
    if embedder_choice == "all":
        target_embedder_names = ["hashing", "nomic"]
    elif embedder_choice == "hashing":
        target_embedder_names = ["hashing"]
    elif embedder_choice == "nomic":
        target_embedder_names = ["nomic"]

    # Pre-flight check: if nomic is requested, verify Ollama and model are available before processing
    embedders: list[Embedder] = []
    for name in target_embedder_names:
        if name == "nomic":
            try:
                emb = OllamaEmbedder(timeout=60.0)
                # Trigger connectivity and model availability check
                _ = emb.digest
                embedders.append(emb)
            except Exception as exc:
                print(
                    f"Error: Ollama or model 'nomic-embed-text' is unavailable ({exc}). "
                    f"Ensure Ollama is running and run `ollama pull nomic-embed-text`.",
                    file=sys.stderr,
                )
                return 1
        else:
            embedders.append(get_embedder(name))

    factory = session_factory if session_factory is not None else SessionLocal
    with factory() as db:
        for embedder in embedders:
            model_name = embedder.name
            if missing_only:
                existing_ids = sa.select(TicketEmbedding.ticket_id).where(
                    TicketEmbedding.model_name == model_name
                )
                stmt = (
                    sa.select(Ticket)
                    .where(~Ticket.id.in_(existing_ids))
                    .order_by(Ticket.id.asc())
                )
            else:
                stmt = sa.select(Ticket).order_by(Ticket.id.asc())

            tickets = db.scalars(stmt).all()
            total = len(tickets)
            if total == 0:
                print(
                    f"No tickets to reindex for {model_name}"
                    + (" (missing-only active)." if missing_only else ".")
                )
                continue

            print(f"Reindexing {total} tickets for {model_name} in batches of {BATCH_SIZE}...")
            processed = 0
            for i in range(0, total, BATCH_SIZE):
                batch = tickets[i : i + BATCH_SIZE]
                texts = [get_text_to_embed(t.title, t.description) for t in batch]

                if hasattr(embedder, "embed_documents"):
                    vectors = embedder.embed_documents(texts)
                else:
                    vectors = embedder.embed(texts)

                now = datetime.now(timezone.utc)
                for ticket, vec in zip(batch, vectors):
                    vec_np = vec.astype(np.float32)
                    existing = db.get(TicketEmbedding, (ticket.id, model_name))
                    if existing:
                        existing.dim = int(vec_np.shape[0])
                        existing.vector = vec_np.tobytes()
                        existing.updated_at = now
                    else:
                        emb = TicketEmbedding.from_numpy(
                            ticket_id=ticket.id,
                            model_name=model_name,
                            vec=vec_np,
                            updated_at=now,
                        )
                        db.add(emb)
                db.commit()
                processed += len(batch)
                print(f"Reindexed {processed}/{total} tickets for {model_name}...")

            print(f"Completed reindexing {processed}/{total} tickets for {model_name}.")

    return 0


if __name__ == "__main__":
    sys.exit(reindex_embeddings(sys.argv[1:]))
