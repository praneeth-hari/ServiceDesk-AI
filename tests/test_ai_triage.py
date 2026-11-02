from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ai.embedder import Embedder, HashingEmbedder, SbertEmbedder, get_embedder, get_text_to_embed
from app.core.config import Settings
from app.models.embedding import TicketEmbedding
from app.models.enums import TicketCategory, TicketPriority, TicketStatus, UserRole
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.ticket import TicketCreate, TicketUpdate
from app.scripts.eval_triage import run_evaluation
from app.scripts.reindex_embeddings import reindex_embeddings
from app.services.tickets import create_ticket, update_ticket
from app.services.triage import find_similar, predict_knn, suggest, sync_ticket_embedding


# ---------------------------------------------------------------------------
# Fake Embedder with deterministic hand-crafted vectors
# ---------------------------------------------------------------------------
class FakeEmbedder:
    """Deterministic test embedder with pre-mapped vectors."""

    def __init__(
        self,
        mapping: dict[str, np.ndarray] | None = None,
        default_vector: np.ndarray | None = None,
    ) -> None:
        self.name = "fake"
        self.dim = 4
        self.mapping = mapping or {}
        self.default_vector = (
            default_vector
            if default_vector is not None
            else np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        )

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        result = []
        for text in texts:
            vec = self.mapping.get(text, self.default_vector)
            # Ensure unit length
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            result.append(vec.astype(np.float32))
        return result


# ---------------------------------------------------------------------------
# 1. Embedder Tests
# ---------------------------------------------------------------------------
def test_hashing_embedder_deterministic_and_unit_norm():
    """Verify HashingEmbedder is deterministic, returns unit length, and handles morphology/typos."""
    embedder = HashingEmbedder(n_features=2048)
    assert embedder.name == "hashing-v2"
    assert embedder.dim == 4096

    text_a = "Wi-Fi disconnected on the 4th floor conference room"
    text_b = "Wi-Fi disconnected on the 4th floor meeting space"
    text_c = "Employee payroll calculation discrepancy for finance"

    vec_a1 = embedder.embed([text_a])[0]
    vec_a2 = embedder.embed([text_a])[0]
    # Determinism
    np.testing.assert_array_almost_equal(vec_a1, vec_a2)

    # Unit norm (L2)
    assert np.isclose(np.linalg.norm(vec_a1), 1.0, atol=1e-5)

    # Similar text scores higher than completely unrelated text
    vec_b = embedder.embed([text_b])[0]
    vec_c = embedder.embed([text_c])[0]

    sim_ab = float(np.dot(vec_a1, vec_b))
    sim_ac = float(np.dot(vec_a1, vec_c))
    assert sim_ab > sim_ac, f"Expected {sim_ab} > {sim_ac}"

    # Morphological variation resilience (char_wb n-grams)
    t_morph1 = "VPN disconnects unexpectedly during meetings"
    t_morph2 = "VPN disconnecting unexpectedly during meetings"
    v_m1 = embedder.embed([t_morph1])[0]
    v_m2 = embedder.embed([t_morph2])[0]
    sim_morph = float(np.dot(v_m1, v_m2))
    assert sim_morph > 0.70, f"Expected morphological similarity > 0.70, got {sim_morph}"


def test_hashing_embedder_empty_list():
    embedder = HashingEmbedder()
    assert embedder.embed([]) == []


def test_embedder_factory():
    h = get_embedder("hashing")
    assert isinstance(h, HashingEmbedder)

    with pytest.raises(ValueError, match="Unknown embedder name 'invalid'"):
        get_embedder("invalid")


def test_sbert_embedder_optional():
    """Optional test for sentence-transformers backend; skips cleanly if missing."""
    st = pytest.importorskip("sentence_transformers")
    sbert = SbertEmbedder()
    assert sbert.name == "sbert"
    assert sbert.dim == 384
    vecs = sbert.embed(["Test ticket issue with VPN connection"])
    assert len(vecs) == 1
    assert vecs[0].shape == (384,)
    assert np.isclose(np.linalg.norm(vecs[0]), 1.0, atol=1e-4)


def test_sbert_embedder_missing_package_error():
    """Verify SbertEmbedder raises clear error indicating requirements-ai.txt if missing."""
    sbert = SbertEmbedder()
    with patch.dict("sys.modules", {"sentence_transformers": None}):
        with pytest.raises(ImportError) as exc_info:
            sbert.embed(["Test text"])
        assert "requirements-ai.txt" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 2. Config & Settings Validation Tests
# ---------------------------------------------------------------------------
def test_config_ai_settings_validation():
    # Valid
    s = Settings(
        AI_EMBEDDER="hashing",
        AI_DUPLICATE_THRESHOLD=0.85,
        AI_MIN_SIMILARITY=0.25,
        AI_KNN_K=3,
        AI_MAX_CANDIDATES=1000,
    )
    assert s.AI_EMBEDDER == "hashing"

    # Invalid embedder
    with pytest.raises(ValueError, match="AI_EMBEDDER must be 'hashing', 'hashing-v2', or 'sbert'"):
        Settings(AI_EMBEDDER="word2vec")

    # Invalid min similarity
    with pytest.raises(ValueError, match="AI_MIN_SIMILARITY must be between 0.0 and 1.0"):
        Settings(AI_MIN_SIMILARITY=1.5)

    # Invalid duplicate threshold
    with pytest.raises(ValueError, match="AI_DUPLICATE_THRESHOLD must be between 0.0 and 1.0"):
        Settings(AI_DUPLICATE_THRESHOLD=-0.1)

    # Min sim > duplicate threshold
    with pytest.raises(ValueError, match="must not exceed AI_DUPLICATE_THRESHOLD"):
        Settings(AI_MIN_SIMILARITY=0.9, AI_DUPLICATE_THRESHOLD=0.7)

    # Invalid K
    with pytest.raises(ValueError, match="AI_KNN_K must be at least 1"):
        Settings(AI_KNN_K=0)

    # Invalid MAX_CANDIDATES
    with pytest.raises(ValueError, match="AI_MAX_CANDIDATES must be at least 1"):
        Settings(AI_MAX_CANDIDATES=0)


# ---------------------------------------------------------------------------
# 3. Pure predict_knn Logic Tests
# ---------------------------------------------------------------------------
def test_predict_knn_weighted_voting():
    """Verify exact similarity-weighted vote and confidence computation."""
    candidates = [
        {"category": TicketCategory.NETWORK, "priority": TicketPriority.HIGH, "similarity": 0.90},
        {"category": TicketCategory.HARDWARE, "priority": TicketPriority.MEDIUM, "similarity": 0.40},
        {"category": TicketCategory.NETWORK, "priority": TicketPriority.MEDIUM, "similarity": 0.30},
    ]
    # Total weight = 0.90 + 0.40 + 0.30 = 1.60
    # Network weight = 0.90 + 0.30 = 1.20 -> winning category
    # Hardware weight = 0.40
    # Priority High = 0.90, Medium = 0.70 -> winning priority = High
    # Confidence = 1.20 / 1.60 = 0.75
    cat, prio, conf = predict_knn(candidates, k=3, min_similarity=0.20)
    assert cat == TicketCategory.NETWORK
    assert prio == TicketPriority.HIGH
    assert conf == 0.75


def test_predict_knn_no_neighbours_or_below_min():
    """Verify returns None suggestions with confidence 0.0 when no candidates qualify."""
    assert predict_knn([], k=5, min_similarity=0.20) == (None, None, 0.0)

    low_candidates = [
        {"category": TicketCategory.NETWORK, "priority": TicketPriority.HIGH, "similarity": 0.15},
        {"category": TicketCategory.EMAIL, "priority": TicketPriority.LOW, "similarity": 0.10},
    ]
    assert predict_knn(low_candidates, k=5, min_similarity=0.20) == (None, None, 0.0)


# ---------------------------------------------------------------------------
# 4. Service & Endpoint Tests: Suggest & Duplicate Detection
# ---------------------------------------------------------------------------
def test_suggest_with_fake_embedder(
    db_session: Session,
    admin_user: User,
    requester_user: User,
    second_requester_user: User,
):
    """
    Test suggest workflow:
    - Resolved tickets vote for category & priority.
    - Open ticket above threshold is detected as possible duplicate.
    - Privacy: requester only sees their own evidence and duplicates.
    """
    now = datetime.now(timezone.utc)
    # Unit vectors in 4D:
    # Query vector: [1, 0, 0, 0]
    # Resolved 1 (sim 1.0): [1, 0, 0, 0] owned by second_requester
    # Resolved 2 (sim 0.707): [0.707, 0.707, 0, 0] owned by requester
    # Open duplicate (sim 1.0): [1, 0, 0, 0] owned by second_requester
    # Open low-sim (sim 0.0): [0, 1, 0, 0] owned by requester
    v_target = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    v_partial = np.array([0.707106, 0.707106, 0.0, 0.0], dtype=np.float32)
    v_ortho = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)

    fake_embedder = FakeEmbedder(
        mapping={
            "Target Problem. Target Problem": v_target,
        },
        default_vector=v_target,
    )

    # 1. Resolved ticket 1 (network, high) owned by other user
    t_res1 = Ticket(
        title="Resolved 1",
        description="Network issue",
        status=TicketStatus.RESOLVED,
        category=TicketCategory.NETWORK,
        priority=TicketPriority.HIGH,
        requester_id=second_requester_user.id,
        created_at=now,
        updated_at=now,
    )
    # 2. Resolved ticket 2 (hardware, low) owned by requester
    t_res2 = Ticket(
        title="Resolved 2",
        description="Hardware issue",
        status=TicketStatus.RESOLVED,
        category=TicketCategory.HARDWARE,
        priority=TicketPriority.LOW,
        requester_id=requester_user.id,
        created_at=now,
        updated_at=now,
    )
    # 3. Open duplicate ticket owned by second_requester
    t_dup = Ticket(
        title="Open Duplicate",
        description="Duplicate open issue",
        status=TicketStatus.OPEN,
        category=TicketCategory.NETWORK,
        priority=TicketPriority.HIGH,
        requester_id=second_requester_user.id,
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([t_res1, t_res2, t_dup])
    db_session.flush()

    # Add embeddings
    emb1 = TicketEmbedding.from_numpy(t_res1.id, fake_embedder.name, v_target)
    emb2 = TicketEmbedding.from_numpy(t_res2.id, fake_embedder.name, v_partial)
    emb_dup = TicketEmbedding.from_numpy(t_dup.id, fake_embedder.name, v_target)
    db_session.add_all([emb1, emb2, emb_dup])
    db_session.commit()

    # --- Run suggest as Admin ---
    admin_result = suggest(
        db=db_session,
        title="Target Problem",
        description="Target Problem",
        current_user=admin_user,
        embedder=fake_embedder,
    )
    assert admin_result["suggested_category"] == TicketCategory.NETWORK
    assert admin_result["suggested_priority"] == TicketPriority.HIGH
    assert len(admin_result["evidence"]) == 2
    # Admin sees the other user's duplicate
    assert len(admin_result["possible_duplicates"]) == 1
    assert admin_result["possible_duplicates"][0]["id"] == t_dup.id

    # --- Run suggest as Requester (Privacy Test) ---
    req_result = suggest(
        db=db_session,
        title="Target Problem",
        description="Target Problem",
        current_user=requester_user,
        embedder=fake_embedder,
    )
    # The aggregated vote still predicts network (uses all tickets)
    assert req_result["suggested_category"] == TicketCategory.NETWORK
    # BUT evidence list only contains requester's own tickets!
    assert len(req_result["evidence"]) == 1
    assert req_result["evidence"][0]["id"] == t_res2.id
    # AND possible_duplicates hides the other user's duplicate!
    assert len(req_result["possible_duplicates"]) == 0


def test_triage_suggest_api_endpoint(client: TestClient, requester_auth_headers: dict[str, str]):
    """Test POST /api/v1/triage/suggest endpoint validation and response."""
    # 1. Successful suggestion request
    resp = client.post(
        "/api/v1/triage/suggest",
        json={"title": "VPN connection drops", "description": "GlobalProtect error code 54"},
        headers=requester_auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "suggested_category" in data
    assert "confidence" in data
    assert data["possible_duplicates"] in ([], None) or isinstance(data["possible_duplicates"], list)
    assert data["embedder"] == get_embedder().name

    # 2. Validation error: empty title
    resp_empty = client.post(
        "/api/v1/triage/suggest",
        json={"title": "", "description": "Valid description"},
        headers=requester_auth_headers,
    )
    assert resp_empty.status_code == 422

    # 3. Unauthenticated request returns 401
    resp_unauth = client.post(
        "/api/v1/triage/suggest",
        json={"title": "Test Title", "description": "Test Desc"},
    )
    assert resp_unauth.status_code == 401


# ---------------------------------------------------------------------------
# 5. Similar Tickets Endpoint Tests
# ---------------------------------------------------------------------------
def test_tickets_similar_permissions_and_exclusion(
    client: TestClient,
    db_session: Session,
    agent_user: User,
    agent_auth_headers: dict[str, str],
    requester_auth_headers: dict[str, str],
):
    """
    Test GET /api/v1/tickets/{id}/similar:
    - 403 for requester
    - 404 for non-existent ticket
    - Excludes target ticket itself
    - Respects limit query parameter
    """
    now = datetime.now(timezone.utc)
    t1 = Ticket(
        title="Network Core Switch Crash",
        description="Core switch port flapping in datacenter",
        status=TicketStatus.OPEN,
        category=TicketCategory.NETWORK,
        priority=TicketPriority.URGENT,
        requester_id=agent_user.id,
        created_at=now,
        updated_at=now,
    )
    t2 = Ticket(
        title="Network Core Switch Reload",
        description="Core switch port flapping after reboot",
        status=TicketStatus.OPEN,
        category=TicketCategory.NETWORK,
        priority=TicketPriority.URGENT,
        requester_id=agent_user.id,
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([t1, t2])
    db_session.flush()

    sync_ticket_embedding(db_session, t1)
    sync_ticket_embedding(db_session, t2)
    db_session.commit()

    # Requester receives 403
    r_req = client.get(f"/api/v1/tickets/{t1.id}/similar", headers=requester_auth_headers)
    assert r_req.status_code == 403

    # Non-existent ticket returns 404
    r_404 = client.get("/api/v1/tickets/99999/similar", headers=agent_auth_headers)
    assert r_404.status_code == 404

    # Agent receives similar tickets excluding t1
    r_agent = client.get(f"/api/v1/tickets/{t1.id}/similar?limit=5", headers=agent_auth_headers)
    assert r_agent.status_code == 200
    similar_list = r_agent.json()
    similar_ids = [item["id"] for item in similar_list]
    assert t1.id not in similar_ids
    assert t2.id in similar_ids

    # Limit parameter validation
    r_invalid_limit = client.get(f"/api/v1/tickets/{t1.id}/similar?limit=50", headers=agent_auth_headers)
    assert r_invalid_limit.status_code == 422


# ---------------------------------------------------------------------------
# 6. Automatic Embedding Sync & Resilience Tests
# ---------------------------------------------------------------------------
def test_ticket_creation_and_update_embedding_sync(db_session: Session, admin_user: User):
    """Verify embeddings are created on ticket creation and updated on text edit."""
    ticket_in = TicketCreate(
        title="Original Title Wi-Fi issue",
        description="Original description of the wireless problem",
        category=TicketCategory.NETWORK,
        priority=TicketPriority.MEDIUM,
    )
    ticket = create_ticket(db_session, ticket_in, admin_user)
    emb = db_session.get(TicketEmbedding, ticket.id)
    assert emb is not None
    assert emb.model_name == get_embedder().name
    original_vector = emb.vector

    # 1. Update only priority or category -> text did not change, embedding unchanged
    update_cat = TicketUpdate(category=TicketCategory.OTHER)
    update_ticket(db_session, ticket.id, update_cat, admin_user)
    emb_after_cat = db_session.get(TicketEmbedding, ticket.id)
    assert emb_after_cat.vector == original_vector

    # 2. Update title -> embedding is refreshed
    update_title = TicketUpdate(title="Updated Title Printer Paper Jam")
    update_ticket(db_session, ticket.id, update_title, admin_user)
    emb_after_title = db_session.get(TicketEmbedding, ticket.id)
    assert emb_after_title.vector != original_vector


def test_failing_embedder_does_not_break_ticket_creation(db_session: Session, admin_user: User):
    """Verify that if the AI embedder fails, ticket creation and updates still succeed."""
    ticket_in = TicketCreate(
        title="Resilience Test Ticket",
        description="Checking that ticket is created even if AI fails",
        category=TicketCategory.NETWORK,
        priority=TicketPriority.LOW,
    )

    with patch("app.services.triage.get_embedder", side_effect=RuntimeError("AI subsystem crash")):
        # Must not raise an exception
        ticket = create_ticket(db_session, ticket_in, admin_user)
        assert ticket is not None
        assert ticket.title == "Resilience Test Ticket"

        # Update should also succeed
        update_in = TicketUpdate(title="Resilience Test Ticket Edited")
        updated = update_ticket(db_session, ticket.id, update_in, admin_user)
        assert updated.title == "Resilience Test Ticket Edited"


# ---------------------------------------------------------------------------
# 7. Script Smoke Tests: Reindex & Eval Scripts
# ---------------------------------------------------------------------------
def test_reindex_embeddings_script(db_session: Session, agent_user: User):
    """Smoke test for reindex_embeddings script."""
    t = Ticket(
        title="Reindex ticket",
        description="Reindex description",
        status=TicketStatus.OPEN,
        category=TicketCategory.SOFTWARE,
        priority=TicketPriority.MEDIUM,
        requester_id=agent_user.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(t)
    db_session.commit()
    target_id = t.id

    from contextlib import contextmanager

    @contextmanager
    def mock_session_local():
        yield db_session

    with patch("app.scripts.reindex_embeddings.SessionLocal", side_effect=mock_session_local):
        exit_code = reindex_embeddings()
        assert exit_code == 0
        emb = db_session.get(TicketEmbedding, target_id)
        assert emb is not None


def test_eval_triage_script_smoke(tmp_path: Path):
    """Smoke test for eval_triage script on a synthetic subset."""
    csv_file = tmp_path / "tiny_eval.csv"
    with open(csv_file, "w", encoding="utf-8") as f:
        f.write("# Synthetic tiny eval dataset\n")
        f.write("title,description,category,priority\n")
        for i in range(15):
            cat = "network" if i % 2 == 0 else "hardware"
            prio = "high" if i % 2 == 0 else "low"
            f.write(f"Problem {i},Description details for ticket {i},{cat},{prio}\n")

    res = run_evaluation(
        embedder_name="hashing",
        k=2,
        min_similarity=0.01,
        csv_path=csv_file,
        tune=True,
    )
    assert res["total_test"] == 3
    assert "overall_category_accuracy" in res
    assert res["tuning_results"] is not None


def test_get_text_to_embed_edge_cases():
    """Verify get_text_to_embed handles title-only, desc-only, and empty strings."""
    assert get_text_to_embed("Title", "Desc") == "Title. Desc"
    assert get_text_to_embed("Title Only", "") == "Title Only"
    assert get_text_to_embed("", "Desc Only") == "Desc Only"
    assert get_text_to_embed("  ", "   ") == ""


def test_sbert_mocked_execution():
    """Verify SbertEmbedder behavior when sentence_transformers is mocked."""
    from unittest.mock import MagicMock
    mock_model = MagicMock()
    mock_model.encode.return_value = [np.array([0.1, 0.2], dtype=np.float32)]

    sbert = SbertEmbedder()
    assert sbert.name == "sbert"
    assert sbert.dim == 384
    assert sbert.embed([]) == []

    with patch.object(sbert, "_load_model", return_value=mock_model):
        res = sbert.embed(["Test text"])
        assert len(res) == 1
        assert res[0].shape == (2,)


def test_triage_empty_vectors_and_zero_weights():
    """Verify suggest and find_similar when embedder returns empty vector list."""
    from unittest.mock import MagicMock
    mock_embedder = MagicMock()
    mock_embedder.name = "mock"
    mock_embedder.embed.return_value = []

    mock_db = MagicMock()
    mock_user = MagicMock()
    mock_user.role = UserRole.ADMIN

    res_suggest = suggest(mock_db, "T", "D", mock_user, embedder=mock_embedder)
    assert res_suggest["suggested_category"] is None
    assert res_suggest["confidence"] == 0.0

    res_similar = find_similar(mock_db, "T", mock_user, embedder=mock_embedder)
    assert res_similar == []


def test_predict_knn_zero_weight_edge_case():
    """Verify predict_knn handles candidates where all similarity weights are zero."""
    candidates = [
        {"category": TicketCategory.NETWORK, "priority": TicketPriority.HIGH, "similarity": 0.0},
    ]
    assert predict_knn(candidates, k=1, min_similarity=0.0) == (None, None, 0.0)
