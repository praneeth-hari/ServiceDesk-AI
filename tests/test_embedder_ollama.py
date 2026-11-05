"""
Unit tests for OllamaEmbedder (app.ai.embedder.OllamaEmbedder).

All HTTP interactions with Ollama are mocked so no running Ollama daemon
is required to execute this test suite.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error

import numpy as np
import pytest

from app.ai.embedder import OllamaEmbedder, get_embedder
from app.ai.dataset import TicketExample
from app.scripts.benchmark_triage import run_knn_method


def _mock_http_response(status_code: int, data: dict):
    body = json.dumps(data).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = body
    resp.getcode.return_value = status_code
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


@pytest.fixture
def mock_ollama_metadata():
    """Mock the /api/version and /api/tags endpoints for nomic-embed-text."""
    def _mock_urlopen(req, *args, **kwargs):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/api/version" in url:
            return _mock_http_response(200, {"version": "0.3.14"})
        if "/api/tags" in url:
            return _mock_http_response(
                200,
                {
                    "models": [
                        {
                            "name": "nomic-embed-text:latest",
                            "digest": "0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f",
                        }
                    ]
                },
            )
        raise urllib.error.URLError("Unexpected URL")

    with patch("urllib.request.urlopen", side_effect=_mock_urlopen):
        yield


def test_ollama_embedder_initialization_and_metadata(tmp_path, mock_ollama_metadata):
    embedder = OllamaEmbedder(
        model_name="nomic-embed-text",
        variant="classification",
        cache_dir=tmp_path / "cache",
    )
    assert embedder.name == "nomic-embed-text"
    assert embedder.dim == 768
    assert embedder.variant == "classification"
    assert embedder.doc_prefix == "classification: "
    assert embedder.query_prefix == "classification: "
    assert embedder.version == "0.3.14"
    assert embedder.digest == "0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f"


def test_ollama_embedder_prefix_variants(tmp_path, mock_ollama_metadata):
    search_emb = OllamaEmbedder(variant="search", cache_dir=tmp_path / "cache_s")
    assert search_emb.doc_prefix == "search_document: "
    assert search_emb.query_prefix == "search_query: "

    class_emb = OllamaEmbedder(variant="classification", cache_dir=tmp_path / "cache_c")
    assert class_emb.doc_prefix == "classification: "
    assert class_emb.query_prefix == "classification: "

    clust_emb = OllamaEmbedder(variant="clustering", cache_dir=tmp_path / "cache_cl")
    assert clust_emb.doc_prefix == "clustering: "
    assert clust_emb.query_prefix == "clustering: "

    none_emb = OllamaEmbedder(variant="none", cache_dir=tmp_path / "cache_n")
    assert none_emb.doc_prefix == ""
    assert none_emb.query_prefix == ""

    with pytest.raises(ValueError, match="Unknown prefix variant"):
        OllamaEmbedder(variant="invalid_variant", cache_dir=tmp_path / "cache_bad")


def test_ollama_embedder_batching_and_l2_normalization(tmp_path, mock_ollama_metadata):
    embedder = OllamaEmbedder(
        variant="classification",
        cache_dir=tmp_path / "cache",
        batch_size=2,
    )

    batch_calls: list[list[str]] = []

    def _mock_call(inputs: list[str]) -> list[list[float]]:
        batch_calls.append(inputs)
        # Return arbitrary unnormalized vectors
        return [[float(i + 1)] * 768 for i in range(len(inputs))]

    embedder._call_ollama_embed = _mock_call

    texts = ["ticket 1", "ticket 2", "ticket 3", "ticket 4", "ticket 5"]
    vecs = embedder.embed(texts)

    assert len(vecs) == 5
    # With batch_size=2, 5 items -> batches of 2, 2, 1
    assert len(batch_calls) == 3
    assert len(batch_calls[0]) == 2
    assert len(batch_calls[1]) == 2
    assert len(batch_calls[2]) == 1

    # Verify prefix was applied to batch inputs
    assert batch_calls[0][0] == "classification: ticket 1"
    assert batch_calls[0][1] == "classification: ticket 2"

    # Verify L2 normalization
    for v in vecs:
        norm = np.linalg.norm(v)
        assert np.isclose(norm, 1.0, atol=1e-6)


def test_ollama_embedder_zero_vector_handling(tmp_path, mock_ollama_metadata):
    embedder = OllamaEmbedder(cache_dir=tmp_path / "cache")
    embedder._call_ollama_embed = lambda inputs: [[0.0] * 768 for _ in inputs]

    vecs = embedder.embed(["empty text"])
    assert len(vecs) == 1
    assert np.all(vecs[0] == 0.0)
    assert vecs[0].dtype == np.float32


def test_ollama_embedder_disk_cache_hits_and_misses(tmp_path, mock_ollama_metadata):
    embedder = OllamaEmbedder(cache_dir=tmp_path / "cache")
    embed_calls = 0

    def _mock_call(inputs: list[str]) -> list[list[float]]:
        nonlocal embed_calls
        embed_calls += 1
        return [[1.0] * 768 for _ in inputs]

    embedder._call_ollama_embed = _mock_call

    texts = ["VPN issue", "Printer broken"]

    # First run: all misses
    res1 = embedder.embed(texts)
    assert embed_calls == 1
    assert embedder.cache_misses == 2
    assert embedder.cache_hits == 0

    # Second run with same texts: all hits from sqlite
    res2 = embedder.embed(texts)
    assert embed_calls == 1  # No additional HTTP calls
    assert embedder.cache_hits == 2
    assert embedder.cache_misses == 2

    # Verify results match identically
    np.testing.assert_allclose(res1[0], res2[0])
    np.testing.assert_allclose(res1[1], res2[1])


def test_ollama_embedder_cache_key_varies_with_prefix_and_digest(tmp_path, mock_ollama_metadata):
    embedder = OllamaEmbedder(cache_dir=tmp_path / "cache")

    text = "Password reset request"
    k_class = embedder.compute_cache_key("classification: ", text)
    k_search = embedder.compute_cache_key("search_document: ", text)
    k_none = embedder.compute_cache_key("", text)

    # Different prefixes must produce different cache keys
    assert k_class != k_search
    assert k_class != k_none
    assert k_search != k_none

    # Changing model digest must produce different cache key
    embedder._digest = "different_digest_123456"
    k_class_new_digest = embedder.compute_cache_key("classification: ", text)
    assert k_class != k_class_new_digest


def test_ollama_embedder_unreachable_error(tmp_path):
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        embedder = OllamaEmbedder(cache_dir=tmp_path / "cache")
        with pytest.raises(RuntimeError, match="Cannot reach Ollama"):
            _ = embedder.digest


def test_ollama_embedder_missing_model_error(tmp_path):
    def _mock_urlopen(req, *args, **kwargs):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/api/version" in url:
            return _mock_http_response(200, {"version": "0.3.14"})
        if "/api/tags" in url:
            return _mock_http_response(
                200,
                {"models": [{"name": "llama3:latest", "digest": "abcdef123"}]},
            )
        raise urllib.error.URLError("Unexpected URL")

    with patch("urllib.request.urlopen", side_effect=_mock_urlopen):
        embedder = OllamaEmbedder(model_name="nomic-embed-text", cache_dir=tmp_path / "cache")
        with pytest.raises(RuntimeError, match="Model 'nomic-embed-text' not found in Ollama"):
            _ = embedder.digest


def test_ollama_embedder_http_404_error_on_embed(tmp_path, mock_ollama_metadata):
    embedder = OllamaEmbedder(cache_dir=tmp_path / "cache")
    # Simulate 404 from /api/embed
    http_err = urllib.error.HTTPError(
        url="http://localhost:11434/api/embed",
        code=404,
        msg="Not Found",
        hdrs={},  # type: ignore
        fp=io.BytesIO(b'{"error": "model not found"}'),
    )

    with patch("urllib.request.urlopen", side_effect=http_err):
        with pytest.raises(RuntimeError, match="Run `ollama pull nomic-embed-text`"):
            embedder._call_ollama_embed(["test text"])


def test_benchmark_triage_skips_nomic_gracefully_when_unreachable():
    """Ensure benchmark triage skips nomic-knn without failing the run if Ollama is down."""
    train_tickets = [
        TicketExample(id="1", text="printer broken", category="hardware", priority="low", difficulty="easy", group="helpdesk")
    ]
    test_tickets = [
        TicketExample(id="2", text="need mouse", category="hardware", priority="low", difficulty="easy", group="helpdesk")
    ]

    with patch("app.scripts.benchmark_triage.get_embedder", side_effect=RuntimeError("Cannot reach Ollama")):
        preds = run_knn_method(
            method_name="nomic-knn",
            train_tickets=train_tickets,
            test_tickets=test_tickets,
        )
        assert preds == []


def test_get_embedder_factory_for_nomic(tmp_path, mock_ollama_metadata):
    emb1 = get_embedder("nomic")
    assert isinstance(emb1, OllamaEmbedder)
    assert emb1.model_name == "nomic-embed-text"

    emb2 = get_embedder("nomic-embed-text")
    assert isinstance(emb2, OllamaEmbedder)

    emb3 = get_embedder("ollama")
    assert isinstance(emb3, OllamaEmbedder)
