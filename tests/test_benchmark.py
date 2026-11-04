"""
Unit tests for the triage benchmark pipeline (app.scripts.benchmark_triage).

Requires NO running Ollama daemon and NO pre-downloaded transformer models.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error

import pytest

from app.ai.dataset import TicketExample
from app.models.enums import TicketCategory, TicketPriority
from app.scripts.benchmark_triage import (
    CATEGORIES,
    PRIORITIES,
    OLLAMA_FORMAT_SCHEMA,
    SYSTEM_PROMPT,
    build_rag_prompt,
    build_zero_shot_prompt,
    call_ollama_chat,
    check_ollama_status,
    compute_confusion_matrix,
    compute_macro_f1,
    compute_mcnemar_exact_test,
    compute_wilson_ci,
    compute_within_one_accuracy,
    evaluate_baselines,
    evaluate_predictions,
    generate_results_markdown,
    run_knn_method,
    run_llm_method,
)
from app.services.triage import predict_knn


def test_wilson_ci_bounds_and_symmetry():
    # Edge case: zero trials
    lower, upper = compute_wilson_ci(0, 0)
    assert lower == 0.0 and upper == 0.0

    # Symmetric case: 50 successes out of 100 trials
    lower, upper = compute_wilson_ci(50, 100)
    assert 0.39 < lower < 0.42
    assert 0.58 < upper < 0.61

    # Boundary cases
    lower_0, upper_0 = compute_wilson_ci(0, 100)
    assert lower_0 == 0.0
    assert 0.0 < upper_0 < 0.05

    lower_100, upper_100 = compute_wilson_ci(100, 100)
    assert 0.95 < lower_100 < 1.0
    assert upper_100 == 1.0


def test_macro_f1_and_per_class():
    true_labels = ["network", "network", "hardware", "software", "access"]
    pred_labels = ["network", "hardware", "hardware", "software", "access"]
    classes = ["network", "hardware", "software", "access", "email", "other"]

    macro_f1, per_class = compute_macro_f1(true_labels, pred_labels, classes)

    assert "network" in per_class
    assert per_class["software"]["f1"] == 1.0
    assert per_class["access"]["f1"] == 1.0
    assert per_class["email"]["f1"] == 0.0  # zero support, zero predictions
    assert 0.0 < macro_f1 < 1.0


def test_within_one_priority():
    # Exactly matching
    assert compute_within_one_accuracy(["low", "medium"], ["low", "medium"]) == 1.0

    # Within one level
    # low -> medium is diff 1 (within one)
    # urgent -> high is diff 1 (within one)
    assert compute_within_one_accuracy(["low", "urgent"], ["medium", "high"]) == 1.0

    # More than one level
    # low -> high is diff 2 (not within one)
    # urgent -> low is diff 3 (not within one)
    assert compute_within_one_accuracy(["low", "urgent"], ["high", "low"]) == 0.0

    # Invalid / None predictions
    assert compute_within_one_accuracy(["low"], ["invalid"]) == 0.0
    assert compute_within_one_accuracy(["high"], [None]) == 0.0


def test_confusion_matrix_structure():
    true_c = ["software", "software", "network"]
    pred_c = ["software", "hardware", "network"]
    classes = ["network", "hardware", "software"]

    cm = compute_confusion_matrix(true_c, pred_c, classes)
    assert cm["software"]["software"] == 1
    assert cm["software"]["hardware"] == 1
    assert cm["network"]["network"] == 1
    assert cm["network"]["software"] == 0


def test_knn_voting_logic():
    # kNN voting rule: similarity-weighted sum
    candidates = [
        {"category": TicketCategory.NETWORK, "priority": TicketPriority.HIGH, "similarity": 0.85},
        {"category": TicketCategory.HARDWARE, "priority": TicketPriority.LOW, "similarity": 0.50},
        {"category": TicketCategory.HARDWARE, "priority": TicketPriority.LOW, "similarity": 0.40},
    ]
    # HARDWARE weight = 0.50 + 0.40 = 0.90
    # NETWORK weight = 0.85
    # Winning category should be HARDWARE
    cat, prio, conf = predict_knn(candidates, k=3, min_similarity=0.12)
    assert cat == TicketCategory.HARDWARE
    assert prio == TicketPriority.LOW
    assert conf > 0.5


def test_prompt_building_strictly_excludes_label_note():
    ticket = TicketExample(
        id="TEST-001",
        text="VPN connectivity dropped\nCannot access internal wiki through GlobalProtect",
        category="network",
        priority="high",
        difficulty="hard",
        group="grp-01",
    )

    # Zero-shot prompt
    zs_prompt = build_zero_shot_prompt(ticket)
    assert "VPN connectivity dropped" in zs_prompt
    assert "label_note" not in zs_prompt
    assert "grp-01" not in zs_prompt

    # System prompt must include canonical definitions for all 6 categories and 4 priorities
    for c in CATEGORIES:
        assert c in SYSTEM_PROMPT
    for p in PRIORITIES:
        assert p in SYSTEM_PROMPT

    # RAG prompt
    ref_ticket = TicketExample(
        id="REF-001",
        text="Wi-Fi unstable in building B\nKeeps disconnecting every 5 minutes",
        category="network",
        priority="medium",
        difficulty="easy",
        group="grp-02",
    )
    rag_prompt = build_rag_prompt(ticket, [ref_ticket])
    assert "Reference Ticket #1" in rag_prompt
    assert "Wi-Fi unstable in building B" in rag_prompt
    assert "Category: network" in rag_prompt
    assert "Priority: medium" in rag_prompt
    assert "VPN connectivity dropped" in rag_prompt
    assert "label_note" not in rag_prompt


def test_llm_prompt_golden_fixture_exact_match():
    fixture_path = Path("tests/fixtures/llm_prompt_golden.json")
    assert fixture_path.is_file(), "Golden prompt fixture must exist"
    golden = json.loads(fixture_path.read_text(encoding="utf-8"))

    ticket_data = golden["ticket"]
    ticket = TicketExample(
        id=ticket_data["id"],
        text=ticket_data["text"],
        category=ticket_data["category"],
        priority=ticket_data["priority"],
        difficulty="easy",
        group="grp-01",
    )
    retrieved = [
        TicketExample(
            id=ex["id"],
            text=ex["text"],
            category=ex["category"],
            priority=ex["priority"],
            difficulty="easy",
            group=f"grp-ref-{idx}",
        )
        for idx, ex in enumerate(golden["retrieved_examples"])
    ]

    built_user_prompt = build_rag_prompt(ticket, retrieved)
    assert built_user_prompt == golden["user_prompt"]
    assert SYSTEM_PROMPT == golden["system_prompt"]
    assert OLLAMA_FORMAT_SCHEMA == golden["format_schema"]


def test_check_ollama_status_offline():
    # When Ollama is offline or endpoint unreachable
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        is_ok, err_msg, digest = check_ollama_status("http://127.0.0.1:99999", "nonexistent-model")
        assert not is_ok
        assert "Could not reach Ollama" in err_msg
        assert digest == ""


def test_call_ollama_chat_valid_mock():
    mock_resp_data = {
        "message": {
            "content": json.dumps({"category": "software", "priority": "high"})
        }
    }
    mock_response = io.BytesIO(json.dumps(mock_resp_data).encode("utf-8"))

    with patch("urllib.request.urlopen", return_value=mock_response):
        cat, prio, latency, is_invalid = call_ollama_chat(
            model_name="llama3.1:8b",
            user_prompt="Ticket: Excel crashed",
        )
        assert cat == "software"
        assert prio == "high"
        assert not is_invalid
        assert latency >= 0.0


def test_call_ollama_chat_invalid_retry_and_fallback():
    # Returns invalid JSON or invalid category/priority labels
    mock_resp_data = {
        "message": {
            "content": json.dumps({"category": "unknown_cat", "priority": "extreme"})
        }
    }
    mock_response = io.BytesIO(json.dumps(mock_resp_data).encode("utf-8"))

    with patch("urllib.request.urlopen", return_value=mock_response):
        cat, prio, latency, is_invalid = call_ollama_chat(
            model_name="llama3.1:8b",
            user_prompt="Ticket: Something broken",
            max_retries=1,
        )
        assert cat is None
        assert prio is None
        assert is_invalid is True


def test_resume_cache_logic(tmp_path: Path):
    cache_file = tmp_path / "cache_llm-test.jsonl"
    cached_rec = {
        "id": "TKT-001",
        "predicted_category": "network",
        "predicted_priority": "high",
        "latency_ms": 12.5,
        "invalid": False,
    }
    cache_file.write_text(json.dumps(cached_rec) + "\n", encoding="utf-8")

    t1 = TicketExample("TKT-001", "Text 1", "network", "high", "easy", "g1")
    t2 = TicketExample("TKT-002", "Text 2", "software", "low", "easy", "g2")

    mock_resp_data = {
        "message": {
            "content": json.dumps({"category": "software", "priority": "low"})
        }
    }

    with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(mock_resp_data).encode("utf-8"))):
        preds = run_llm_method(
            method_name="llm-test",
            model_name="llama3.1:8b",
            train_tickets=[],
            test_tickets=[t1, t2],
            output_dir=tmp_path,
            resume=True,
        )

        assert len(preds) == 2
        # First ticket came from cache (latency 12.5ms)
        assert preds[0]["id"] == "TKT-001"
        assert preds[0]["latency_ms"] == 12.5

        # Second ticket was evaluated and written to cache
        assert preds[1]["id"] == "TKT-002"
        assert preds[1]["predicted_category"] == "software"

        # Check cache file now has 2 lines
        lines = [line.strip() for line in cache_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(lines) == 2


def test_evaluate_predictions_metrics():
    test_tickets = [
        TicketExample("1", "Text 1", "network", "high", "easy", "g1"),
        TicketExample("2", "Text 2", "software", "low", "hard", "g2"),
    ]
    preds = [
        {"id": "1", "predicted_category": "network", "predicted_priority": "high"},
        {"id": "2", "predicted_category": "hardware", "predicted_priority": "low"},  # category wrong
    ]

    metrics = evaluate_predictions(test_tickets, preds)
    cat_m = metrics["category_metrics"]
    prio_m = metrics["priority_metrics"]

    assert cat_m["accuracy"] == 0.5
    assert cat_m["easy_accuracy"] == 1.0
    assert cat_m["hard_accuracy"] == 0.0
    assert prio_m["accuracy"] == 1.0


def test_hashing_knn_execution():
    train_t = [
        TicketExample("TR-1", "Wi-Fi not connecting in cafeteria", "network", "medium", "easy", "g1"),
        TicketExample("TR-2", "Install PyCharm Professional", "software", "low", "easy", "g2"),
    ]
    test_t = [
        TicketExample("TS-1", "Wi-Fi keeps dropping in kitchen", "network", "medium", "easy", "g3"),
    ]

    preds = run_knn_method("hashing-knn", train_t, test_t, k=1, min_similarity=0.01)
    assert len(preds) == 1
    assert preds[0]["predicted_category"] in CATEGORIES
    assert preds[0]["predicted_priority"] in PRIORITIES


def test_sentence_transformers_skip_if_missing():
    pytest.importorskip("sentence_transformers")
    train_t = [
        TicketExample("TR-1", "Wi-Fi not connecting", "network", "medium", "easy", "g1"),
    ]
    test_t = [
        TicketExample("TS-1", "Wi-Fi drops", "network", "medium", "easy", "g2"),
    ]
    preds = run_knn_method("minilm-knn", train_t, test_t, k=1, min_similarity=0.01)
    assert len(preds) == 1


def test_compute_mcnemar_exact_test():
    # Symmetric / no discordant pairs
    b, c, p = compute_mcnemar_exact_test([True, False], [True, False])
    assert b == 0 and c == 0
    assert p == 1.0

    # Equal discordant pairs
    b, c, p = compute_mcnemar_exact_test([True, False], [False, True])
    assert b == 1 and c == 1
    assert p == 1.0

    # Asymmetric: 10 vs 1
    # correct_a: 10 True where B is False; correct_b: 1 True where A is False
    corr_a = [True] * 10 + [False] * 1 + [True] * 5
    corr_b = [False] * 10 + [True] * 1 + [True] * 5
    b, c, p = compute_mcnemar_exact_test(corr_a, corr_b)
    assert b == 10 and c == 1
    assert p < 0.05

    # Known benchmark values: b=18, c=5
    corr_a_rag = [True] * 18 + [False] * 5
    corr_b_mini = [False] * 18 + [True] * 5
    b, c, p = compute_mcnemar_exact_test(corr_a_rag, corr_b_mini)
    assert b == 18 and c == 5
    assert abs(p - 0.010622) < 1e-5

    # Length mismatch raises ValueError
    with pytest.raises(ValueError):
        compute_mcnemar_exact_test([True], [True, False])


def test_generate_results_markdown(tmp_path: Path):
    out_file = tmp_path / "RESULTS.md"
    test_tickets = [
        TicketExample("1", "Text 1", "network", "high", "easy", "g1"),
        TicketExample("2", "Text 2", "software", "low", "hard", "g2"),
    ]
    baselines = {
        "majority_class": {
            "category_accuracy": 0.5,
            "category_ci_95": (0.2, 0.8),
            "category_macro_f1": 0.5,
            "priority_accuracy": 0.5,
            "priority_ci_95": (0.2, 0.8),
            "within_one_accuracy": 1.0,
            "hard_category_accuracy": 0.5,
        },
        "random_guess": {
            "analytical_category_accuracy": 0.1667,
            "analytical_priority_accuracy": 0.25,
            "empirical_category_accuracy": 0.5,
            "category_ci_95": (0.2, 0.8),
            "category_macro_f1": 0.5,
            "priority_accuracy": 0.5,
            "priority_ci_95": (0.2, 0.8),
            "within_one_accuracy": 1.0,
            "hard_category_accuracy": 0.5,
        },
    }
    results = {
        "hashing-knn": {
            "metrics": {
                "category_metrics": {
                    "accuracy": 0.5,
                    "ci_95": (0.2, 0.8),
                    "macro_f1": 0.5,
                    "confusion_matrix": {"network": {"network": 1}, "software": {"software": 1}},
                    "hard_accuracy": 0.5,
                },
                "priority_metrics": {
                    "accuracy": 0.5,
                    "ci_95": (0.2, 0.8),
                    "within_one_accuracy": 1.0,
                },
            },
            "predictions": [
                {"id": "1", "predicted_category": "network", "predicted_priority": "high"},
                {"id": "2", "predicted_category": "software", "predicted_priority": "low"},
            ],
            "mean_latency_ms": 1.0,
        }
    }

    generate_results_markdown(results, baselines, test_tickets, out_file)
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "# Ticket Triage Benchmark Evaluation Report" in content
    assert "hashing-knn" in content


