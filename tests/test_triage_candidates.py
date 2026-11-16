"""
Candidate scoring for AI triage (suggest / find_similar) reads stored embeddings in chunks and
loads ticket text only for the tickets that are returned. These tests check that this gives the
same answers as scoring everything at once, and that it keeps memory low.
"""
import tracemalloc

import numpy as np
import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.embedding import TicketEmbedding
from app.models.enums import TicketCategory, TicketPriority, TicketStatus
from app.models.ticket import Ticket
from app.models.user import User
from app.services import triage
from app.services.triage import _score_candidates, find_similar, suggest

MODEL = "test-embed"
STATUSES = list(TicketStatus)


class FakeEmbedder:
    """Returns one fixed unit vector for any text, so tests control similarities exactly."""

    name = MODEL

    def __init__(self, vector: np.ndarray) -> None:
        self._vector = vector
        self.dim = int(vector.shape[0])

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        return [self._vector for _ in texts]


def _unit(rng: np.random.Generator, dim: int) -> np.ndarray:
    vec = rng.normal(size=dim).astype(np.float32)
    return vec / np.linalg.norm(vec)


def _add_tickets(
    db: Session,
    requester_ids: list[int],
    count: int,
    dim: int,
    seed: int = 1,
) -> list[Ticket]:
    """Add `count` tickets (requesters in round-robin) with random embeddings; returns them oldest first."""
    rng = np.random.default_rng(seed)
    tickets = []
    for i in range(count):
        ticket = Ticket(
            title=f"Ticket {i}",
            description=f"Description of ticket {i} " * 5,
            status=STATUSES[i % len(STATUSES)],
            priority=list(TicketPriority)[i % 4],
            category=list(TicketCategory)[i % 6],
            requester_id=requester_ids[i % len(requester_ids)],
        )
        db.add(ticket)
        db.flush()
        db.add(TicketEmbedding.from_numpy(ticket.id, MODEL, _unit(rng, dim)))
        tickets.append(ticket)
    db.flush()
    return tickets


def _query_embedder(dim: int) -> FakeEmbedder:
    return FakeEmbedder(_unit(np.random.default_rng(99), dim))


@pytest.mark.parametrize("chunk_size", [1, 2, 5, 11, 12, 13, 1000])
def test_results_do_not_depend_on_chunk_size(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    agent_user: User,
    requester_user: User,
    chunk_size: int,
):
    """Scoring in chunks of any size gives exactly the same suggestions and similar tickets."""
    _add_tickets(db_session, [requester_user.id, agent_user.id], count=12, dim=16)
    embedder = _query_embedder(16)

    monkeypatch.setattr(triage, "_CANDIDATE_CHUNK_SIZE", 10_000)
    expected_similar = find_similar(db_session, "q", agent_user, limit=8, embedder=embedder)
    expected_suggest = suggest(db_session, "Title", "Description", agent_user, embedder=embedder)
    assert len(expected_similar) == 8

    monkeypatch.setattr(triage, "_CANDIDATE_CHUNK_SIZE", chunk_size)
    assert find_similar(db_session, "q", agent_user, limit=8, embedder=embedder) == expected_similar
    assert suggest(db_session, "Title", "Description", agent_user, embedder=embedder) == expected_suggest


def test_candidate_cap_keeps_the_newest_tickets(
    monkeypatch: pytest.MonkeyPatch, db_session: Session, requester_user: User
):
    """AI_MAX_CANDIDATES limits scoring to the newest tickets, newest first, whatever the chunk size."""
    tickets = _add_tickets(db_session, [requester_user.id], count=10, dim=8)
    newest_ids = [t.id for t in reversed(tickets)][:7]

    monkeypatch.setattr(settings, "AI_MAX_CANDIDATES", 7)
    monkeypatch.setattr(triage, "_CANDIDATE_CHUNK_SIZE", 3)
    scored = _score_candidates(db_session, _query_embedder(8).embed(["q"])[0], MODEL)

    assert [item["id"] for item in scored] == newest_ids


def test_requester_filter_and_excluded_ticket_apply_before_the_cap(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    requester_user: User,
    second_requester_user: User,
):
    """A requester's own older tickets are still found when newer tickets from others fill the cap."""
    own = _add_tickets(db_session, [requester_user.id], count=3, dim=8, seed=1)
    _add_tickets(db_session, [second_requester_user.id], count=6, dim=8, seed=2)

    monkeypatch.setattr(settings, "AI_MAX_CANDIDATES", 3)
    monkeypatch.setattr(triage, "_CANDIDATE_CHUNK_SIZE", 2)
    embedder = _query_embedder(8)

    results = find_similar(db_session, "q", requester_user, limit=10, embedder=embedder)
    assert sorted(r["id"] for r in results) == sorted(t.id for t in own)

    results = find_similar(
        db_session, "q", requester_user, limit=10, embedder=embedder, exclude_ticket_id=own[0].id
    )
    assert sorted(r["id"] for r in results) == sorted(t.id for t in own[1:])


def test_titles_and_descriptions_are_read_only_for_returned_tickets(
    monkeypatch: pytest.MonkeyPatch, db_session: Session, agent_user: User, requester_user: User
):
    """The queries that load candidates skip the text columns; text is read once for the results."""
    _add_tickets(db_session, [requester_user.id], count=9, dim=8)
    monkeypatch.setattr(triage, "_CANDIDATE_CHUNK_SIZE", 4)

    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    bind = db_session.get_bind()
    event.listen(bind, "before_cursor_execute", record)
    try:
        results = find_similar(db_session, "q", agent_user, limit=2, embedder=_query_embedder(8))
    finally:
        event.remove(bind, "before_cursor_execute", record)

    assert len(results) == 2
    assert all(r["title"] and r["description"] for r in results)

    candidate_queries = [s for s in statements if "ticket_embeddings" in s and "vector" in s]
    assert len(candidate_queries) == 3  # 9 candidates in chunks of 4
    assert all("tickets.description" not in s and "tickets.title" not in s for s in candidate_queries)

    text_queries = [s for s in statements if "tickets.description" in s]
    assert len(text_queries) == 1  # one read of title and description, for the 2 results only


def test_scoring_uses_a_fraction_of_the_memory_of_loading_everything(
    monkeypatch: pytest.MonkeyPatch, db_session: Session, agent_user: User, requester_user: User
):
    """Peak memory follows the chunk size, not the number of candidates (4096-value vectors, as in production)."""
    dim = 4096
    _add_tickets(db_session, [requester_user.id], count=400, dim=dim)
    db_session.expire_all()
    embedder = _query_embedder(dim)
    all_vectors_bytes = 400 * dim * 4  # 6.5 MB; loading everything used to peak at about 3x this

    monkeypatch.setattr(triage, "_CANDIDATE_CHUNK_SIZE", 50)
    tracemalloc.start()
    try:
        find_similar(db_session, "q", agent_user, limit=5, embedder=embedder)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert peak < all_vectors_bytes, f"peak {peak / 1e6:.1f} MB for {all_vectors_bytes / 1e6:.1f} MB of vectors"
