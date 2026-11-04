"""
Unit tests for LLM-assisted triage module and fallback mechanisms.
All tests run without requiring a running Ollama server or sentence-transformers.
"""

from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch
import urllib.error
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ai.llm_triage import (
    CATEGORIES,
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_URL,
    OLLAMA_FORMAT_SCHEMA,
    PRIORITIES,
    SYSTEM_PROMPT,
    build_rag_prompt,
    build_zero_shot_prompt,
    check_ollama_status,
    extract_ticket_text,
    parse_and_validate_llm_response,
    triage_with_llm,
)
from app.core.config import Settings, settings
from app.models.enums import TicketCategory, TicketPriority, UserRole
from app.models.user import User
from app.schemas.triage import TriageSuggestResponse
from app.services.triage import suggest


# ---------------------------------------------------------------------------
# 1. Config & Settings Validation
# ---------------------------------------------------------------------------
def test_ai_triage_settings_defaults():
    """Verify default values of LLM triage configuration."""
    s = Settings(_env_file=None)
    assert s.AI_TRIAGE_MODE == "knn"
    assert s.OLLAMA_BASE_URL == "http://127.0.0.1:11434"
    assert s.AI_LLM_MODEL == "llama3.1:8b"
    assert s.AI_LLM_TIMEOUT_SECONDS == 30
    assert s.AI_LLM_EXAMPLES == 5


def test_ai_triage_settings_validation():
    """Verify AI_TRIAGE_MODE accepts only 'knn' or 'llm'."""
    assert Settings(_env_file=None, AI_TRIAGE_MODE="knn").AI_TRIAGE_MODE == "knn"
    assert Settings(_env_file=None, AI_TRIAGE_MODE="llm").AI_TRIAGE_MODE == "llm"

    with pytest.raises(ValueError, match="must be 'knn' or 'llm'"):
        Settings(_env_file=None, AI_TRIAGE_MODE="invalid_mode")

    with pytest.raises(ValueError, match="must be 'knn' or 'llm'"):
        Settings(_env_file=None, AI_TRIAGE_MODE="rag")


# ---------------------------------------------------------------------------
# 2. Schema and Prompt Definition Tests
# ---------------------------------------------------------------------------
def test_triage_suggest_response_schema():
    """Verify TriageSuggestResponse backwards compatibility and new fields."""
    # Default method is knn, fallback_reason is None
    resp_default = TriageSuggestResponse(
        suggested_category=TicketCategory.NETWORK,
        suggested_priority=TicketPriority.HIGH,
        confidence=0.85,
        similar_tickets=[],
        possible_duplicates=[],
        embedder="hashing-v2",
    )
    assert resp_default.method == "knn"
    assert resp_default.fallback_reason is None

    # LLM RAG response (confidence is None)
    resp_llm = TriageSuggestResponse(
        suggested_category=TicketCategory.SOFTWARE,
        suggested_priority=TicketPriority.MEDIUM,
        confidence=None,
        similar_tickets=[],
        possible_duplicates=[],
        embedder="hashing-v2",
        method="llm-rag",
        fallback_reason=None,
    )
    assert resp_llm.method == "llm-rag"
    assert resp_llm.confidence is None
    assert resp_llm.fallback_reason is None

    # Fallback to kNN response
    resp_fallback = TriageSuggestResponse(
        suggested_category=TicketCategory.SOFTWARE,
        suggested_priority=TicketPriority.MEDIUM,
        confidence=0.70,
        similar_tickets=[],
        possible_duplicates=[],
        embedder="hashing-v2",
        method="knn",
        fallback_reason="Ollama connection refused",
    )
    assert resp_fallback.method == "knn"
    assert resp_fallback.fallback_reason == "Ollama connection refused"


def test_ollama_format_schema_structure():
    """Verify Ollama JSON schema specifies category and priority enums."""
    assert OLLAMA_FORMAT_SCHEMA["type"] == "object"
    assert "category" in OLLAMA_FORMAT_SCHEMA["properties"]
    assert "priority" in OLLAMA_FORMAT_SCHEMA["properties"]
    assert set(OLLAMA_FORMAT_SCHEMA["properties"]["category"]["enum"]) == set(CATEGORIES)
    assert set(OLLAMA_FORMAT_SCHEMA["properties"]["priority"]["enum"]) == set(PRIORITIES)
    assert set(OLLAMA_FORMAT_SCHEMA["required"]) == {"category", "priority"}


# ---------------------------------------------------------------------------
# 3. LLM Response Parsing and Validation
# ---------------------------------------------------------------------------
def test_parse_and_validate_llm_response():
    """Verify JSON parsing and strict taxonomy validation."""
    # Valid output
    cat, prio, err = parse_and_validate_llm_response('{"category": "hardware", "priority": "urgent"}')
    assert cat == "hardware"
    assert prio == "urgent"
    assert err is None

    # Normalization (stripping and lowercase)
    cat, prio, err = parse_and_validate_llm_response('{"category": " ACCESS ", "priority": " High "}')
    assert cat == "access"
    assert prio == "high"
    assert err is None

    # Empty or whitespace
    cat, prio, err = parse_and_validate_llm_response("")
    assert (cat, prio) == (None, None)
    assert err == "empty response from LLM"

    # Malformed JSON
    cat, prio, err = parse_and_validate_llm_response("not valid json")
    assert (cat, prio) == (None, None)
    assert "invalid JSON" in err

    # Non-dict JSON
    cat, prio, err = parse_and_validate_llm_response('["hardware", "urgent"]')
    assert (cat, prio) == (None, None)
    assert "not an object" in err

    # Invalid category
    cat, prio, err = parse_and_validate_llm_response('{"category": "spaceship", "priority": "low"}')
    assert (cat, prio) == (None, None)
    assert "invalid category 'spaceship'" in err

    # Invalid priority
    cat, prio, err = parse_and_validate_llm_response('{"category": "network", "priority": "emergency"}')
    assert (cat, prio) == (None, None)
    assert "invalid priority 'emergency'" in err

    # Both invalid
    cat, prio, err = parse_and_validate_llm_response('{"category": "foo", "priority": "bar"}')
    assert (cat, prio) == (None, None)
    assert "invalid category 'foo' and priority 'bar'" in err


# ---------------------------------------------------------------------------
# 4. Ollama Pre-check and Chat Calling (Mocked HTTP)
# ---------------------------------------------------------------------------
def test_check_ollama_status_installed():
    """Verify check_ollama_status returns True when model is present."""
    fake_response_data = json.dumps({
        "models": [
            {"name": "llama3.1:8b", "model": "llama3.1:8b", "digest": "sha256:abc12345"},
            {"name": "mistral:latest", "model": "mistral:latest", "digest": "sha256:def67890"},
        ]
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = fake_response_data
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        is_ok, err, digest = check_ollama_status(model_name="llama3.1:8b")
        assert is_ok is True
        assert err == ""
        assert digest == "sha256:abc12345"


def test_check_ollama_status_model_not_installed():
    """Verify check_ollama_status returns False when model is not installed."""
    fake_response_data = json.dumps({
        "models": [
            {"name": "mistral:7b", "model": "mistral:7b", "digest": "sha256:def67890"},
        ]
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = fake_response_data
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        is_ok, err, digest = check_ollama_status(model_name="llama3.1:8b")
        assert is_ok is False
        assert "is not installed" in err


def test_check_ollama_status_connection_error():
    """Verify check_ollama_status handles connection failure gracefully."""
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        is_ok, err, digest = check_ollama_status()
        assert is_ok is False
        assert "Could not reach Ollama" in err


def test_triage_with_llm_success():
    """Verify triage_with_llm executes end-to-end when Ollama responds with valid JSON."""
    mock_tags_data = json.dumps({"models": [{"name": "llama3.1:8b", "digest": "sha256:abc"}]}).encode("utf-8")
    mock_chat_data = json.dumps({
        "message": {"role": "assistant", "content": '{"category": "access", "priority": "high"}'}
    }).encode("utf-8")

    def mock_urlopen(req, timeout=None):
        m = MagicMock()
        m.__enter__.return_value = m
        if "api/tags" in req.full_url:
            m.read.return_value = mock_tags_data
        else:
            m.read.return_value = mock_chat_data
        return m

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        cat, prio, latency, err = triage_with_llm(
            ticket_text="VPN MFA token locked out",
            retrieved_examples=[],
            model_name="llama3.1:8b",
        )
        assert cat == "access"
        assert prio == "high"
        assert latency >= 0.0
        assert err is None


@pytest.mark.parametrize(
    "error_type,side_effect,expected_substr",
    [
        ("connection", urllib.error.URLError("Connection refused"), "connection error"),
        ("timeout", TimeoutError("Request timed out"), "timed out"),
        ("http_500", urllib.error.HTTPError(url="", code=500, msg="Internal Server Error", hdrs=None, fp=None), "HTTP error 500"),
    ],
)
def test_triage_with_llm_network_errors(error_type, side_effect, expected_substr):
    """Verify triage_with_llm captures network, timeout, and HTTP errors."""
    mock_tags_data = json.dumps({"models": [{"name": "llama3.1:8b", "digest": "sha256:abc"}]}).encode("utf-8")

    def mock_urlopen(req, timeout=None):
        if "api/tags" in req.full_url:
            m = MagicMock()
            m.__enter__.return_value = m
            m.read.return_value = mock_tags_data
            return m
        raise side_effect

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        cat, prio, latency, err = triage_with_llm(
            ticket_text="Sample ticket",
            retrieved_examples=[],
            max_retries=0,
        )
        assert (cat, prio) == (None, None)
        assert expected_substr in err


def test_triage_with_llm_invalid_json_fallback():
    """Verify triage_with_llm falls back when LLM outputs invalid JSON."""
    mock_tags_data = json.dumps({"models": [{"name": "llama3.1:8b", "digest": "sha256:abc"}]}).encode("utf-8")
    mock_chat_data = json.dumps({
        "message": {"role": "assistant", "content": "I think this is hardware urgent"}
    }).encode("utf-8")

    def mock_urlopen(req, timeout=None):
        m = MagicMock()
        m.__enter__.return_value = m
        if "api/tags" in req.full_url:
            m.read.return_value = mock_tags_data
        else:
            m.read.return_value = mock_chat_data
        return m

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        cat, prio, latency, err = triage_with_llm(
            ticket_text="Sample ticket",
            retrieved_examples=[],
            max_retries=0,
        )
        assert (cat, prio) == (None, None)
        assert "Invalid LLM output: invalid JSON" in err


def test_triage_with_llm_invalid_label_fallback():
    """Verify triage_with_llm falls back when LLM outputs labels outside allowed taxonomy."""
    mock_tags_data = json.dumps({"models": [{"name": "llama3.1:8b", "digest": "sha256:abc"}]}).encode("utf-8")
    mock_chat_data = json.dumps({
        "message": {"role": "assistant", "content": '{"category": "cloud_infrastructure", "priority": "critical"}'}
    }).encode("utf-8")

    def mock_urlopen(req, timeout=None):
        m = MagicMock()
        m.__enter__.return_value = m
        if "api/tags" in req.full_url:
            m.read.return_value = mock_tags_data
        else:
            m.read.return_value = mock_chat_data
        return m

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        cat, prio, latency, err = triage_with_llm(
            ticket_text="Sample ticket",
            retrieved_examples=[],
            max_retries=0,
        )
        assert (cat, prio) == (None, None)
        assert "Invalid LLM output: invalid category" in err


# ---------------------------------------------------------------------------
# 5. Service Layer Integration and Fallbacks
# ---------------------------------------------------------------------------
def test_suggest_service_default_knn_mode():
    """In default knn mode, triage service uses kNN directly without invoking LLM."""
    mock_db = MagicMock()
    mock_user = MagicMock()
    mock_user.role = UserRole.ADMIN

    mock_embedder = MagicMock()
    mock_embedder.name = "hashing-v2"
    mock_embedder.embed.return_value = [[0.1, 0.2]]

    with patch.object(settings, "AI_TRIAGE_MODE", "knn"), \
         patch("app.services.triage.find_similar", return_value=[]), \
         patch("app.services.triage.predict_knn", return_value=(TicketCategory.HARDWARE, TicketPriority.LOW, 0.75)), \
         patch("app.services.triage.triage_with_llm") as mock_llm:

        res = suggest(mock_db, "Laptop battery swollen", "Trackpad lifting", mock_user, embedder=mock_embedder)

        assert res["method"] == "knn"
        assert res["fallback_reason"] is None
        assert res["suggested_category"] == TicketCategory.HARDWARE
        assert res["suggested_priority"] == TicketPriority.LOW
        assert res["confidence"] == 0.75
        mock_llm.assert_not_called()


def test_suggest_service_llm_mode_success():
    """In llm mode, triage service overrides kNN suggestion with LLM prediction."""
    mock_db = MagicMock()
    mock_user = MagicMock()
    mock_user.role = UserRole.ADMIN

    mock_embedder = MagicMock()
    mock_embedder.name = "hashing-v2"
    mock_embedder.embed.return_value = [[0.1, 0.2]]

    candidates = [
        {
            "id": 1,
            "title": "Historical ref",
            "description": "ref desc",
            "category": TicketCategory.NETWORK,
            "priority": TicketPriority.LOW,
            "similarity": 0.80,
        }
    ]

    with patch.object(settings, "AI_TRIAGE_MODE", "llm"), \
         patch("app.services.triage.find_similar", return_value=candidates), \
         patch("app.services.triage.predict_knn", return_value=(TicketCategory.NETWORK, TicketPriority.LOW, 0.60)), \
         patch("app.services.triage.triage_with_llm", return_value=("access", "urgent", 120.0, None)) as mock_llm:

        res = suggest(mock_db, "AD Account locked out", "Locked after 3 attempts", mock_user, embedder=mock_embedder)

        assert res["method"] == "llm-rag"
        assert res["fallback_reason"] is None
        assert res["suggested_category"] == TicketCategory.ACCESS
        assert res["suggested_priority"] == TicketPriority.URGENT
        assert res["confidence"] is None
        mock_llm.assert_called_once()


def test_suggest_service_llm_mode_fallback_on_failure():
    """In llm mode, if Ollama fails, service falls back to kNN and preserves suggestions."""
    mock_db = MagicMock()
    mock_user = MagicMock()
    mock_user.role = UserRole.ADMIN

    mock_embedder = MagicMock()
    mock_embedder.name = "hashing-v2"
    mock_embedder.embed.return_value = [[0.1, 0.2]]

    with patch.object(settings, "AI_TRIAGE_MODE", "llm"), \
         patch("app.services.triage.find_similar", return_value=[]), \
         patch("app.services.triage.predict_knn", return_value=(TicketCategory.SOFTWARE, TicketPriority.MEDIUM, 0.55)), \
         patch("app.services.triage.triage_with_llm", return_value=(None, None, 10.0, "Ollama connection error: Connection refused")):

        res = suggest(mock_db, "Excel formula error", "Formula produces #VALUE", mock_user, embedder=mock_embedder)

        assert res["method"] == "knn"
        assert res["fallback_reason"] == "Ollama connection error: Connection refused"
        assert res["suggested_category"] == TicketCategory.SOFTWARE
        assert res["suggested_priority"] == TicketPriority.MEDIUM
        assert res["confidence"] == 0.55


def test_suggest_service_llm_mode_unexpected_exception_fallback():
    """Verify that even an unexpected exception in LLM branch falls back gracefully to kNN."""
    mock_db = MagicMock()
    mock_user = MagicMock()
    mock_user.role = UserRole.ADMIN

    mock_embedder = MagicMock()
    mock_embedder.name = "hashing-v2"
    mock_embedder.embed.return_value = [[0.1, 0.2]]

    with patch.object(settings, "AI_TRIAGE_MODE", "llm"), \
         patch("app.services.triage.find_similar", return_value=[]), \
         patch("app.services.triage.predict_knn", return_value=(TicketCategory.OTHER, TicketPriority.LOW, 0.40)), \
         patch("app.services.triage.triage_with_llm", side_effect=RuntimeError("Unexpected Ollama crash")):

        res = suggest(mock_db, "General question", "Where is the cafeteria?", mock_user, embedder=mock_embedder)

        assert res["method"] == "knn"
        assert "Unexpected Ollama crash" in res["fallback_reason"]
        assert res["suggested_category"] == TicketCategory.OTHER
        assert res["suggested_priority"] == TicketPriority.LOW


# ---------------------------------------------------------------------------
# 6. API Route Integration Tests (POST /api/v1/triage/suggest)
# ---------------------------------------------------------------------------
def test_api_triage_suggest_knn_mode(client: TestClient, requester_auth_headers: dict[str, str]):
    """Verify POST /api/v1/triage/suggest endpoint returns method='knn' and fallback_reason=null."""
    with patch.object(settings, "AI_TRIAGE_MODE", "knn"):
        resp = client.post(
            "/api/v1/triage/suggest",
            json={"title": "Wi-Fi not connecting", "description": "Cannot connect to office Wi-Fi network"},
            headers=requester_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["method"] == "knn"
        assert data["fallback_reason"] is None
        assert "suggested_category" in data
        assert "suggested_priority" in data


def test_api_triage_suggest_llm_mode_success(client: TestClient, requester_auth_headers: dict[str, str]):
    """Verify endpoint returns method='llm-rag' when LLM succeeds."""
    with patch.object(settings, "AI_TRIAGE_MODE", "llm"), \
         patch("app.services.triage.triage_with_llm", return_value=("software", "high", 80.0, None)):

        resp = client.post(
            "/api/v1/triage/suggest",
            json={"title": "Photoshop crash", "description": "Crashes on startup with kernel error"},
            headers=requester_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["method"] == "llm-rag"
        assert data["fallback_reason"] is None
        assert data["suggested_category"] == "software"
        assert data["suggested_priority"] == "high"
        assert data["confidence"] is None


def test_api_triage_suggest_llm_mode_fallback_never_returns_500(client: TestClient, requester_auth_headers: dict[str, str]):
    """Verify endpoint falls back to knn and never returns 500 when Ollama fails."""
    with patch.object(settings, "AI_TRIAGE_MODE", "llm"), \
         patch("app.services.triage.triage_with_llm", return_value=(None, None, 5.0, "Ollama connection error: Connection refused")):

        resp = client.post(
            "/api/v1/triage/suggest",
            json={"title": "Photoshop crash", "description": "Crashes on startup with kernel error"},
            headers=requester_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["method"] == "knn"
        assert data["fallback_reason"] == "Ollama connection error: Connection refused"
        assert "suggested_category" in data


def test_compute_cosine_similarities_empty_vectors_guard():
    """Verify _compute_cosine_similarities safely returns [] when candidate iterator yields no vectors."""
    import numpy as np
    from app.services.triage import _compute_cosine_similarities
    query_vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    # An empty generator/iterator is truthy (bool(iter([])) is True), but has 0 records
    empty_iter = iter([])
    res = _compute_cosine_similarities(query_vec, empty_iter)
    assert res == []
