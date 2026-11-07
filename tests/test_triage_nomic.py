from contextlib import contextmanager
from datetime import datetime, timezone
import logging
from unittest.mock import MagicMock, patch
import numpy as np
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.ai.embedder import HashingEmbedder, OllamaEmbedder, get_embedder, get_text_to_embed
from app.core.config import settings
from app.models.embedding import TicketEmbedding
from app.models.enums import TicketCategory, TicketPriority, TicketStatus, UserRole
from app.models.ticket import Ticket
from app.models.user import User
from app.scripts.reindex_embeddings import reindex_embeddings
from app.services.tickets import create_ticket
from app.services.triage import find_similar, suggest, sync_ticket_embedding
from app.schemas.ticket import TicketCreate


def _make_dummy_ticket(
    db: Session,
    user: User,
    title: str = "Dummy ticket",
    status: TicketStatus = TicketStatus.RESOLVED,
    category: TicketCategory = TicketCategory.HARDWARE,
    priority: TicketPriority = TicketPriority.HIGH,
) -> Ticket:
    now = datetime.now(timezone.utc)
    ticket = Ticket(
        title=title,
        description=f"Description for {title}",
        status=status,
        category=category,
        priority=priority,
        requester_id=user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(ticket)
    db.flush()
    return ticket


def test_composite_pk_two_rows_for_same_ticket(db_session: Session, requester_user: User):
    """Verify ticket_embeddings can hold two rows for the same ticket with different model_name without error."""
    t = _make_dummy_ticket(db_session, requester_user, title="Dual embed ticket")

    now = datetime.now(timezone.utc)
    v_hashing = np.ones(4096, dtype=np.float32) / np.sqrt(4096)
    v_nomic = np.ones(768, dtype=np.float32) / np.sqrt(768)

    emb_h = TicketEmbedding.from_numpy(
        ticket_id=t.id,
        model_name="hashing-v2",
        vec=v_hashing,
        updated_at=now,
    )
    emb_n = TicketEmbedding.from_numpy(
        ticket_id=t.id,
        model_name="nomic-embed-text",
        vec=v_nomic,
        updated_at=now,
    )

    db_session.add(emb_h)
    db_session.add(emb_n)
    db_session.flush()

    h_row = db_session.get(TicketEmbedding, (t.id, "hashing-v2"))
    n_row = db_session.get(TicketEmbedding, (t.id, "nomic-embed-text"))

    assert h_row is not None
    assert h_row.dim == 4096
    assert n_row is not None
    assert n_row.dim == 768
    assert len(t.embeddings) == 2


def test_sync_ticket_embedding_dual_and_single(db_session: Session, requester_user: User, monkeypatch):
    """
    Verify sync_ticket_embedding:
    - with hashing writes only hashing-v2
    - with nomic writes both hashing-v2 and nomic-embed-text rows
    """
    t1 = _make_dummy_ticket(db_session, requester_user, title="Hashing only")

    # 1. Default hashing
    monkeypatch.setattr(settings, "AI_EMBEDDER", "hashing")
    sync_ticket_embedding(db_session, t1)

    assert db_session.get(TicketEmbedding, (t1.id, "hashing-v2")) is not None
    assert db_session.get(TicketEmbedding, (t1.id, "nomic-embed-text")) is None

    # 2. When nomic is active
    t2 = _make_dummy_ticket(db_session, requester_user, title="Nomic active")
    monkeypatch.setattr(settings, "AI_EMBEDDER", "nomic")

    dummy_nomic_vec = np.ones(768, dtype=np.float32) / np.sqrt(768)
    mock_nomic = MagicMock()
    mock_nomic.name = "nomic-embed-text"
    mock_nomic.dim = 768
    mock_nomic.embed_documents.return_value = [dummy_nomic_vec]

    with patch("app.services.triage.get_embedder", side_effect=lambda name=None: mock_nomic if name in ("nomic", "nomic-embed-text") else HashingEmbedder()):
        sync_ticket_embedding(db_session, t2)

    assert db_session.get(TicketEmbedding, (t2.id, "hashing-v2")) is not None
    assert db_session.get(TicketEmbedding, (t2.id, "nomic-embed-text")) is not None


def test_spaces_never_mixed_in_candidate_queries(db_session: Session, requester_user: User):
    """
    Verify vectors from different spaces are never mixed in cosine similarity.
    Queries for hashing-v2 only match hashing-v2 rows, and nomic only matches nomic rows.
    """
    t_hash = _make_dummy_ticket(db_session, requester_user, title="Hash Ticket")
    t_nomic = _make_dummy_ticket(db_session, requester_user, title="Nomic Ticket")

    now = datetime.now(timezone.utc)
    v_h = np.ones(4096, dtype=np.float32) / np.sqrt(4096)
    v_n = np.ones(768, dtype=np.float32) / np.sqrt(768)

    db_session.add(
        TicketEmbedding.from_numpy(ticket_id=t_hash.id, model_name="hashing-v2", vec=v_h, updated_at=now)
    )
    db_session.add(
        TicketEmbedding.from_numpy(ticket_id=t_nomic.id, model_name="nomic-embed-text", vec=v_n, updated_at=now)
    )
    db_session.flush()

    # Query hashing-v2
    hash_stmt = (
        sa.select(TicketEmbedding, Ticket)
        .join(Ticket, TicketEmbedding.ticket_id == Ticket.id)
        .where(TicketEmbedding.model_name == "hashing-v2")
    )
    hash_candidates = db_session.execute(hash_stmt).all()
    assert len(hash_candidates) == 1
    assert hash_candidates[0][0].model_name == "hashing-v2"
    assert hash_candidates[0][0].dim == 4096

    # Query nomic-embed-text
    nomic_stmt = (
        sa.select(TicketEmbedding, Ticket)
        .join(Ticket, TicketEmbedding.ticket_id == Ticket.id)
        .where(TicketEmbedding.model_name == "nomic-embed-text")
    )
    nomic_candidates = db_session.execute(nomic_stmt).all()
    assert len(nomic_candidates) == 1
    assert nomic_candidates[0][0].model_name == "nomic-embed-text"
    assert nomic_candidates[0][0].dim == 768


def test_fallback_on_nomic_unreachable(db_session: Session, requester_user: User, monkeypatch):
    """Fallback on nomic unreachable: mock Ollama to raise ConnectionError, call suggest(), assert fallback."""
    monkeypatch.setattr(settings, "AI_EMBEDDER", "nomic")
    t1 = _make_dummy_ticket(db_session, requester_user, title="Printer broken", status=TicketStatus.RESOLVED)

    now = datetime.now(timezone.utc)
    v_h = np.ones(4096, dtype=np.float32) / np.sqrt(4096)
    v_n = np.ones(768, dtype=np.float32) / np.sqrt(768)
    db_session.add(TicketEmbedding.from_numpy(ticket_id=t1.id, model_name="hashing-v2", vec=v_h, updated_at=now))
    db_session.add(TicketEmbedding.from_numpy(ticket_id=t1.id, model_name="nomic-embed-text", vec=v_n, updated_at=now))
    db_session.flush()

    mock_nomic = MagicMock()
    mock_nomic.name = "nomic-embed-text"
    mock_nomic.embed_query.side_effect = ConnectionError("Ollama connection refused")

    with patch("app.services.triage.get_embedder", side_effect=lambda name=None: mock_nomic if name in ("nomic", "nomic-embed-text") else HashingEmbedder()):
        res = suggest(db_session, "Printer broken", "The printer is jamming", current_user=requester_user)

    assert res["embedder"] == "hashing-v2"
    assert res["embedder_fallback_reason"] == "nomic_unreachable"


def test_fallback_on_nomic_timeout(db_session: Session, requester_user: User, monkeypatch):
    """Fallback on nomic timeout: mock Ollama to raise TimeoutError, call suggest(), assert fallback."""
    monkeypatch.setattr(settings, "AI_EMBEDDER", "nomic")
    t1 = _make_dummy_ticket(db_session, requester_user, title="VPN error", status=TicketStatus.RESOLVED)

    now = datetime.now(timezone.utc)
    v_h = np.ones(4096, dtype=np.float32) / np.sqrt(4096)
    v_n = np.ones(768, dtype=np.float32) / np.sqrt(768)
    db_session.add(TicketEmbedding.from_numpy(ticket_id=t1.id, model_name="hashing-v2", vec=v_h, updated_at=now))
    db_session.add(TicketEmbedding.from_numpy(ticket_id=t1.id, model_name="nomic-embed-text", vec=v_n, updated_at=now))
    db_session.flush()

    mock_nomic = MagicMock()
    mock_nomic.name = "nomic-embed-text"
    mock_nomic.embed_query.side_effect = TimeoutError("Timed out after 3.0s")

    with patch("app.services.triage.get_embedder", side_effect=lambda name=None: mock_nomic if name in ("nomic", "nomic-embed-text") else HashingEmbedder()):
        res = suggest(db_session, "VPN error", "Cannot connect to VPN", current_user=requester_user)

    assert res["embedder"] == "hashing-v2"
    assert res["embedder_fallback_reason"] == "nomic_unreachable"


def test_fallback_on_zero_nomic_embeddings(db_session: Session, requester_user: User, monkeypatch):
    """Fallback on zero nomic embeddings: database has hashing vectors only, assert nomic_no_embeddings."""
    monkeypatch.setattr(settings, "AI_EMBEDDER", "nomic")
    t1 = _make_dummy_ticket(db_session, requester_user, title="Email down", status=TicketStatus.RESOLVED)

    now = datetime.now(timezone.utc)
    v_h = np.ones(4096, dtype=np.float32) / np.sqrt(4096)
    db_session.add(TicketEmbedding.from_numpy(ticket_id=t1.id, model_name="hashing-v2", vec=v_h, updated_at=now))
    db_session.flush()

    res = suggest(db_session, "Email down", "Cannot reach outlook", current_user=requester_user)

    assert res["embedder"] == "hashing-v2"
    assert res["embedder_fallback_reason"] == "nomic_no_embeddings"


def test_incomplete_index_warning(db_session: Session, requester_user: User, monkeypatch, caplog):
    """Incomplete index warning: 10 hashing vectors and 5 nomic vectors; assert warning logged and nomic is used."""
    monkeypatch.setattr(settings, "AI_EMBEDDER", "nomic")

    now = datetime.now(timezone.utc)
    v_h = np.ones(4096, dtype=np.float32) / np.sqrt(4096)
    v_n = np.ones(768, dtype=np.float32) / np.sqrt(768)

    for i in range(10):
        t = _make_dummy_ticket(db_session, requester_user, title=f"Ticket {i}", status=TicketStatus.RESOLVED)
        db_session.add(TicketEmbedding.from_numpy(ticket_id=t.id, model_name="hashing-v2", vec=v_h, updated_at=now))
        if i < 5:
            db_session.add(TicketEmbedding.from_numpy(ticket_id=t.id, model_name="nomic-embed-text", vec=v_n, updated_at=now))
    db_session.flush()

    mock_nomic = MagicMock()
    mock_nomic.name = "nomic-embed-text"
    mock_nomic.embed_query.return_value = [v_n]

    with caplog.at_level(logging.WARNING):
        with patch("app.services.triage.get_embedder", side_effect=lambda name=None: mock_nomic if name in ("nomic", "nomic-embed-text") else HashingEmbedder()):
            res = suggest(db_session, "Ticket query", "Problem description", current_user=requester_user)

    assert res["embedder"] == "nomic-embed-text"
    assert res["embedder_fallback_reason"] is None
    assert any("Incomplete nomic embedding index: 5 nomic vectors vs 10 hashing vectors" in rec.message for rec in caplog.records)


def test_ticket_creation_and_update_succeed_when_ollama_unreachable(db_session: Session, requester_user: User, monkeypatch):
    """Ticket creation and update succeed even when Ollama is unreachable; hashing vector is still written."""
    monkeypatch.setattr(settings, "AI_EMBEDDER", "nomic")

    mock_nomic = MagicMock()
    mock_nomic.name = "nomic-embed-text"
    mock_nomic.embed_documents.side_effect = ConnectionError("Ollama is down")

    with patch("app.services.triage.get_embedder", side_effect=lambda name=None: mock_nomic if name in ("nomic", "nomic-embed-text") else HashingEmbedder()):
        ticket = create_ticket(
            db=db_session,
            ticket_in=TicketCreate(
                title="Broken laptop screen",
                description="Screen has horizontal pink lines",
                category=TicketCategory.HARDWARE,
                priority=TicketPriority.MEDIUM,
            ),
            current_user=requester_user,
        )

    assert ticket.id is not None
    # Hashing vector must still be written
    h_emb = db_session.get(TicketEmbedding, (ticket.id, "hashing-v2"))
    assert h_emb is not None
    assert h_emb.dim == 4096
    # Nomic failed gracefully and was not written
    n_emb = db_session.get(TicketEmbedding, (ticket.id, "nomic-embed-text"))
    assert n_emb is None


def test_reindex_script(db_session: Session, requester_user: User, monkeypatch):
    """Reindex script test: --embedder nomic creates nomic vectors; --missing-only skips existing; idempotent."""
    t1 = _make_dummy_ticket(db_session, requester_user, title="Reindex 1")
    t2 = _make_dummy_ticket(db_session, requester_user, title="Reindex 2")
    db_session.flush()

    dummy_vec = np.ones(768, dtype=np.float32) / np.sqrt(768)
    mock_nomic = MagicMock()
    mock_nomic.name = "nomic-embed-text"
    mock_nomic.dim = 768
    mock_nomic.digest = "testdigest123"
    mock_nomic.embed_documents.return_value = [dummy_vec, dummy_vec]

    @contextmanager
    def _test_session_cm():
        yield db_session

    with patch("app.scripts.reindex_embeddings.get_embedder", side_effect=lambda name: mock_nomic if name in ("nomic", "nomic-embed-text") else HashingEmbedder()):
        # Run 1: index nomic
        exit_code = reindex_embeddings(["--embedder", "nomic"], session_factory=_test_session_cm)
        assert exit_code == 0

        assert db_session.get(TicketEmbedding, (t1.id, "nomic-embed-text")) is not None
        assert db_session.get(TicketEmbedding, (t2.id, "nomic-embed-text")) is not None

        # Run 2: missing-only should find 0 tickets to reindex
        mock_nomic.embed_documents.reset_mock()
        exit_code2 = reindex_embeddings(["--embedder", "nomic", "--missing-only"], session_factory=_test_session_cm)
        assert exit_code2 == 0
        mock_nomic.embed_documents.assert_not_called()


def test_similar_and_duplicates_stay_on_hashing(db_session: Session, requester_user: User, agent_user: User, monkeypatch):
    """
    With AI_EMBEDDER=nomic:
    1. find_similar strictly queries hashing-v2 and embeds query with HashingEmbedder.
    2. possible_duplicates in suggest() strictly uses hashing-v2 space.
    3. LLM RAG candidate pool strictly uses hashing-v2 space.
    The nomic embedder is ONLY invoked for kNN suggestion voting.
    If nomic is ever called for find_similar, duplicate detection, or RAG, it raises AssertionError.
    """
    import inspect
    monkeypatch.setattr(settings, "AI_EMBEDDER", "nomic")
    monkeypatch.setattr(settings, "AI_TRIAGE_MODE", "llm")

    now = datetime.now(timezone.utc)
    t_open = _make_dummy_ticket(
        db_session,
        requester_user,
        title="Active printer problem",
        status=TicketStatus.OPEN,
    )
    t_res = _make_dummy_ticket(
        db_session,
        requester_user,
        title="Resolved printer problem",
        status=TicketStatus.RESOLVED,
    )

    h_emb = HashingEmbedder()
    v_h_open = h_emb.embed([get_text_to_embed(t_open.title, t_open.description)])[0]
    v_h_res = h_emb.embed([get_text_to_embed(t_res.title, t_res.description)])[0]

    v_n = np.ones(768, dtype=np.float32) / np.sqrt(768)

    db_session.add(TicketEmbedding.from_numpy(ticket_id=t_open.id, model_name="hashing-v2", vec=v_h_open, updated_at=now))
    db_session.add(TicketEmbedding.from_numpy(ticket_id=t_open.id, model_name="nomic-embed-text", vec=v_n, updated_at=now))
    db_session.add(TicketEmbedding.from_numpy(ticket_id=t_res.id, model_name="hashing-v2", vec=v_h_res, updated_at=now))
    db_session.add(TicketEmbedding.from_numpy(ticket_id=t_res.id, model_name="nomic-embed-text", vec=v_n, updated_at=now))
    db_session.flush()

    mock_nomic = MagicMock()
    mock_nomic.name = "nomic-embed-text"
    nomic_calls = []

    def guarded_embed_query(texts):
        # Inspect caller stack: ensure nomic is never called by find_similar, duplicates, or RAG
        stack_funcs = [frame.function for frame in inspect.stack()]
        if "find_similar" in stack_funcs:
            raise AssertionError("Nomic embedder called by find_similar (must use hashing-v2)!")
        nomic_calls.append("knn_suggest")
        return [v_n]

    mock_nomic.embed_query.side_effect = guarded_embed_query
    mock_nomic.embed.side_effect = guarded_embed_query

    with patch(
        "app.services.triage.get_embedder",
        side_effect=lambda name=None: mock_nomic if name in ("nomic", "nomic-embed-text") else HashingEmbedder(),
    ):
        # 1. find_similar defaults to hashing-v2 and never calls nomic
        sims = find_similar(db_session, "Active printer problem", current_user=agent_user)
        assert len(sims) >= 1
        assert sims[0]["id"] == t_open.id
        assert len(nomic_calls) == 0, "Nomic was called during find_similar"

        # 2. suggest() duplicate detection and RAG examples use hashing-v2, while kNN voting uses nomic
        captured_rag = []

        def mock_llm_triage(ticket_text, retrieved_examples, **kwargs):
            captured_rag.extend(retrieved_examples)
            return TicketCategory.HARDWARE.value, TicketPriority.HIGH.value, 10.0, None

        with patch("app.services.triage.triage_with_llm", side_effect=mock_llm_triage):
            res = suggest(
                db_session,
                "Active printer problem",
                "Description for Active printer problem",
                current_user=requester_user,
            )

        # kNN used nomic
        assert res["embedder"] == "nomic-embed-text"
        assert res["embedder_fallback_reason"] is None
        assert len(nomic_calls) == 1, "Nomic should only be called once for kNN query vector"

        # Duplicate detection used hashing space
        assert len(res["possible_duplicates"]) >= 1
        assert res["possible_duplicates"][0]["id"] == t_open.id

        # LLM RAG examples retrieved from hashing space
        assert len(captured_rag) >= 1
        assert captured_rag[0]["id"] == t_res.id


def test_no_double_counting_when_dual_embeddings_present(
    db_session: Session, agent_user: User, requester_user: User
):
    """
    Verify that when tickets have multiple embedding rows (e.g. hashing-v2 and nomic-embed-text),
    find_similar and suggest never double-count candidate tickets or return duplicate IDs.
    """
    now = datetime.now(timezone.utc)
    t_res = _make_dummy_ticket(
        db_session,
        requester_user,
        title="Resolved dual embed ticket",
        status=TicketStatus.RESOLVED,
    )
    t_open = _make_dummy_ticket(
        db_session,
        requester_user,
        title="Open duplicate dual embed ticket",
        status=TicketStatus.OPEN,
    )

    h_emb = HashingEmbedder()
    v_h_res = h_emb.embed([get_text_to_embed(t_res.title, t_res.description)])[0]
    v_h_open = h_emb.embed([get_text_to_embed(t_open.title, t_open.description)])[0]

    v_n_res = np.ones(768, dtype=np.float32) / np.sqrt(768)
    v_n_open = np.ones(768, dtype=np.float32) / np.sqrt(768)

    # Insert two rows for each ticket
    db_session.add(TicketEmbedding.from_numpy(t_res.id, "hashing-v2", v_h_res, now))
    db_session.add(TicketEmbedding.from_numpy(t_res.id, "nomic-embed-text", v_n_res, now))
    db_session.add(TicketEmbedding.from_numpy(t_open.id, "hashing-v2", v_h_open, now))
    db_session.add(TicketEmbedding.from_numpy(t_open.id, "nomic-embed-text", v_n_open, now))
    db_session.flush()

    # 1. find_similar should return each ticket at most once
    sims = find_similar(db_session, "Resolved dual embed ticket", current_user=agent_user)
    ticket_ids = [s["id"] for s in sims]
    assert len(ticket_ids) == len(set(ticket_ids)), "find_similar double-counted tickets"

    # 2. suggest() with nomic should return each ticket at most once in evidence and possible_duplicates
    mock_nomic = MagicMock()
    mock_nomic.name = "nomic-embed-text"
    mock_nomic.embed_query.return_value = [v_n_res]

    with patch(
        "app.services.triage.get_embedder",
        side_effect=lambda name=None: mock_nomic if name in ("nomic", "nomic-embed-text") else HashingEmbedder(),
    ):
        res = suggest(
            db_session,
            "Resolved dual embed ticket",
            "Description for Resolved dual embed ticket",
            current_user=agent_user,
        )

    evidence_ids = [e["id"] for e in res["evidence"]]
    assert len(evidence_ids) == len(set(evidence_ids)), "evidence double-counted tickets"

    dup_ids = [d["id"] for d in res["possible_duplicates"]]
    assert len(dup_ids) == len(set(dup_ids)), "possible_duplicates double-counted tickets"



def test_migration_0012_sqlite(tmp_path, monkeypatch):
    """Migration test: run migration 0012 up, down -1, up against SQLite db, asserting row counts and composite PK."""
    import alembic.config
    import alembic.command

    db_path = tmp_path / "migration_test.db"
    db_url = f"sqlite:///{db_path}"

    monkeypatch.setattr(settings, "DATABASE_URL", db_url)
    monkeypatch.setenv("DATABASE_URL", db_url)

    cfg = alembic.config.Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)

    # 1. Upgrade to 0011 (single PK)
    alembic.command.upgrade(cfg, "0011")

    # Insert a ticket and an embedding
    engine = sa.create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(sa.text("""
            INSERT INTO users (id, email, hashed_password, full_name, role, is_active, created_at)
            VALUES (1, 'u@ex.com', 'hash', 'U', 'requester', 1, '2026-01-01')
        """))
        conn.execute(sa.text("""
            INSERT INTO tickets (id, title, description, status, priority, category, requester_id, created_at, updated_at)
            VALUES (1, 'Mig Ticket', 'Desc', 'open', 'low', 'hardware', 1, '2026-01-01', '2026-01-01')
        """))
        conn.execute(sa.text("""
            INSERT INTO ticket_embeddings (ticket_id, model_name, dim, vector, updated_at)
            VALUES (1, 'hashing-v2', 4096, X'00', '2026-01-01')
        """))

    # 2. Upgrade to 0012 (composite PK)
    alembic.command.upgrade(cfg, "0012")

    with engine.begin() as conn:
        # Check that we can insert a second embedding for ticket 1 with model nomic-embed-text
        conn.execute(sa.text("""
            INSERT INTO ticket_embeddings (ticket_id, model_name, dim, vector, updated_at)
            VALUES (1, 'nomic-embed-text', 768, X'01', '2026-01-01')
        """))
        count = conn.execute(sa.text("SELECT COUNT(*) FROM ticket_embeddings WHERE ticket_id = 1")).scalar()
        assert count == 2

    # 3. Downgrade to 0011
    alembic.command.downgrade(cfg, "-1")

    with engine.begin() as conn:
        count = conn.execute(sa.text("SELECT COUNT(*) FROM ticket_embeddings WHERE ticket_id = 1")).scalar()
        assert count == 1
        model = conn.execute(sa.text("SELECT model_name FROM ticket_embeddings WHERE ticket_id = 1")).scalar()
        assert model == "hashing-v2"

    # 4. Re-upgrade to head (0012)
    alembic.command.upgrade(cfg, "head")

    with engine.begin() as conn:
        count = conn.execute(sa.text("SELECT COUNT(*) FROM ticket_embeddings WHERE ticket_id = 1")).scalar()
        assert count == 1
