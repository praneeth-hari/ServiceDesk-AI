"""
Unit tests for keyword-stuffing benchmark scripts and report generation.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from app.ai.dataset import TicketExample
from app.scripts.benchmark_stuffing import (
    evaluate_injection_tickets,
    evaluate_knn_batch,
    get_stuffing_style,
    load_jsonl,
    run_benchmark,
    run_step1_cv,
    run_step2_selection,
    run_step3_eval,
)
from app.scripts.generate_stuffing_report import generate_report, get_lf_sha256


def _make_dummy_ticket(id_: str, cat: str = "network", prio: str = "medium") -> TicketExample:
    return TicketExample(
        id=id_,
        text=f"Ticket {id_} content wifi vpn issue",
        category=cat,
        priority=prio,
        difficulty="easy",
        group="triage",
    )


def test_get_stuffing_style():
    assert get_stuffing_style("STUFF-001") == "keyword_list"
    assert get_stuffing_style("STUFF-012") == "keyword_list"
    assert get_stuffing_style("STUFF-013") == "repeated_words"
    assert get_stuffing_style("STUFF-016") == "repeated_words"
    assert get_stuffing_style("STUFF-017") == "interleaved"
    assert get_stuffing_style("STUFF-020") == "interleaved"
    assert get_stuffing_style("INVALID") == "unknown"


def test_load_jsonl(tmp_path):
    p = tmp_path / "test.jsonl"
    p.write_text('{"id": 1}\n\n{"id": 2}\n', encoding="utf-8")
    loaded = load_jsonl(p)
    assert len(loaded) == 2
    assert loaded[0]["id"] == 1


def test_evaluate_knn_batch_and_injection():
    train_tickets = [_make_dummy_ticket(f"TR-{i}", cat="network", prio="medium") for i in range(5)]
    inj_tickets = [
        {
            "id": "STUFF-001",
            "title": "Email failure",
            "description": "Please help. outlook email mailbox",
            "injected_target": "email",
            "injected_field": "category",
        }
    ]
    succ, by_style, per_ticket = evaluate_injection_tickets(
        train_tickets, inj_tickets, cap_train=None, cap_query=None
    )
    assert len(per_ticket) == 1
    assert per_ticket[0]["id"] == "STUFF-001"
    assert "keyword_list" in by_style


def test_run_step1_cv_and_step2_selection(tmp_path):
    train_tickets = []
    cats = ["network", "hardware", "software", "access", "email", "other"]
    for i in range(30):
        cat = cats[i % len(cats)]
        train_tickets.append(_make_dummy_ticket(f"TR-{i}", cat=cat))

    cv_results = run_step1_cv(train_tickets, tmp_path, n_splits=2)
    assert "baseline" in cv_results
    assert (tmp_path / "step1_cv.json").exists()

    stuffing_tickets = [
        {
            "id": f"STUFF-{i:03d}",
            "title": "Test",
            "description": "wifi vpn network",
            "injected_target": "network",
            "injected_field": "category",
        }
        for i in range(1, 21)
    ]
    step2 = run_step2_selection(train_tickets, stuffing_tickets, cv_results, tmp_path)
    assert (tmp_path / "step2_selection.json").exists()
    assert "baseline" in step2


def test_run_step3_eval_and_generate_report(tmp_path):
    train_tickets = [_make_dummy_ticket(f"TR-{i}") for i in range(10)]
    mock_test = [_make_dummy_ticket(f"TS-{i}") for i in range(10)]
    mock_heldout_v1 = [
        {
            "id": f"HELD-{i:03d}",
            "title": "A",
            "description": "B",
            "attack_type": "lexical_stuffing" if i < 3 else "other",
            "injected_target": "access",
            "injected_field": "category",
        }
        for i in range(30)
    ]
    mock_heldout_v2 = [
        {
            "id": f"IND-{i:03d}",
            "title": "A",
            "description": "B",
            "attack_type": "lexical_stuffing" if i < 5 else "other",
            "injected_target": "access",
            "injected_field": "category",
        }
        for i in range(30)
    ]
    mock_dev = [
        {
            "id": f"DEV-{i:03d}",
            "title": "A",
            "description": "B",
            "injected_target": "access",
            "injected_field": "category",
        }
        for i in range(40)
    ]

    with patch("app.scripts.benchmark_stuffing.load_split", return_value=mock_test), \
         patch("app.scripts.benchmark_stuffing.load_jsonl") as mock_load_jsonl:
        mock_load_jsonl.side_effect = [mock_heldout_v1, mock_heldout_v2, mock_dev]
        step3 = run_step3_eval(train_tickets, "A2", tmp_path)
        assert (tmp_path / "step3_eval.json").exists()
        assert step3["winner"] == "A2"

    # Also test report generation with step3 present
    prereg_p = tmp_path / "prereg.md"
    prereg_p.write_text("# Prereg", encoding="utf-8")
    stuff_p = tmp_path / "stuff.jsonl"
    stuff_p.write_text("{}", encoding="utf-8")
    out_md = tmp_path / "STUFFING.md"

    # Create dummy step1 and step2 files in tmp_path
    cv_data = {
        "baseline": {
            "name": "baseline",
            "cap_train": None,
            "cap_query": None,
            "category_accuracy": 0.60,
            "priority_accuracy": 0.54,
            "cat_delta_pp": 0.0,
            "prio_delta_pp": 0.0,
            "eligible": True,
        },
        "A2": {
            "name": "A2",
            "cap_train": None,
            "cap_query": 2,
            "category_accuracy": 0.60,
            "priority_accuracy": 0.54,
            "cat_delta_pp": 0.0,
            "prio_delta_pp": 0.0,
            "eligible": True,
        },
    }
    (tmp_path / "step1_cv.json").write_text(json.dumps(cv_data), encoding="utf-8")

    step2_data = {
        "n": 20,
        "baseline": {"attack_successes": 5, "attack_success_rate": 0.25, "by_style": {"keyword_list": 2, "repeated_words": 2, "interleaved": 1}},
        "candidates": {
            "A2": {"attack_successes": 5, "attack_success_rate": 0.25, "reduction_pct": 0.0, "by_style": {"keyword_list": 2, "repeated_words": 2, "interleaved": 1}}
        },
        "stopped": False,
        "winner": "A2",
    }
    (tmp_path / "step2_selection.json").write_text(json.dumps(step2_data), encoding="utf-8")

    rep = generate_report(tmp_path, prereg_p, stuff_p, out_md)
    assert "# Benchmark Report" in rep
    assert out_md.exists()
