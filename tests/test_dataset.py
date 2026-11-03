"""
Unit tests for the ServiceDesk600 dataset pipeline and dataset loader.

Tests use isolated temporary files (tmp_path) and do not depend on the real dataset files.
"""

import csv
import json
from pathlib import Path
import pytest

from app.ai.dataset import load_split, TicketExample
from app.scripts.build_dataset import (
    load_and_validate_batches,
    compute_near_duplicates_and_groups,
    apply_corrections_if_present,
    split_train_test,
    run_pipeline,
)


def _make_ticket(
    id_val: str = "NET-001",
    title: str = "Wi-Fi disconnected in Tokyo",
    description: str = "Unable to connect to the office Wi-Fi from the 3rd floor sales area.",
    category: str = "network",
    priority: str = "high",
    difficulty: str = "easy",
    label_note: str = "Wi-Fi connection issue affecting sales team.",
    group: str | None = None,
) -> dict:
    t = {
        "id": id_val,
        "title": title,
        "description": description,
        "category": category,
        "priority": priority,
        "difficulty": difficulty,
        "label_note": label_note,
    }
    if group is not None:
        t["group"] = group
    return t


def test_bad_rows_are_rejected(tmp_path: Path):
    """Rows with invalid JSON, missing/empty fields, invalid enums, or short lengths must be rejected."""
    batch_file = tmp_path / "batch_01.jsonl"
    lines = [
        # 1. Valid row
        json.dumps(_make_ticket("VAL-001")),
        # 2. Invalid JSON syntax
        "{not valid json here",
        # 3. Missing required field 'category'
        json.dumps({
            "id": "BAD-001",
            "title": "Valid title",
            "description": "Valid description long enough",
            "priority": "low",
            "difficulty": "easy",
            "label_note": "note",
        }),
        # 4. Empty field 'title'
        json.dumps(_make_ticket("BAD-002", title="   ")),
        # 5. Invalid category enum value
        json.dumps(_make_ticket("BAD-003", category="teleportation")),
        # 6. Invalid priority enum value
        json.dumps(_make_ticket("BAD-004", priority="catastrophic")),
        # 7. Invalid difficulty enum value
        json.dumps(_make_ticket("BAD-005", difficulty="impossible")),
        # 8. Title too short (< 3 characters)
        json.dumps(_make_ticket("BAD-006", title="ab")),
        # 9. Description too short (< 10 characters)
        json.dumps(_make_ticket("BAD-007", description="too short")),
    ]
    batch_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    valid_tickets, rejected_rows, batch_counts, missing = load_and_validate_batches(tmp_path)

    assert len(valid_tickets) == 1
    assert valid_tickets[0]["id"] == "VAL-001"
    assert len(rejected_rows) == 8

    reasons = [r["reason"] for r in rejected_rows]
    assert any("Invalid JSON" in r for r in reasons)
    assert any("Missing field" in r and "category" in r for r in reasons)
    assert any("Empty field" in r and "title" in r for r in reasons)
    assert any("Invalid category" in r for r in reasons)
    assert any("Invalid priority" in r for r in reasons)
    assert any("Invalid difficulty" in r for r in reasons)
    assert any("Title too short" in r for r in reasons)
    assert any("Description too short" in r for r in reasons)


def test_duplicate_ids_are_rejected(tmp_path: Path):
    """When a ticket id appears more than once, the duplicate occurrence is rejected."""
    batch_file = tmp_path / "batch_01.jsonl"
    t1 = _make_ticket("DUP-001", title="First occurrence")
    t2 = _make_ticket("DUP-001", title="Second occurrence with same id")

    batch_file.write_text(json.dumps(t1) + "\n" + json.dumps(t2) + "\n", encoding="utf-8")

    valid_tickets, rejected_rows, _, _ = load_and_validate_batches(tmp_path)
    assert len(valid_tickets) == 1
    assert valid_tickets[0]["title"] == "First occurrence"

    assert len(rejected_rows) == 1
    assert "Duplicate id 'DUP-001'" in rejected_rows[0]["reason"]
    assert rejected_rows[0]["line_number"] == 2


def test_near_duplicates_share_group_and_never_straddle_split(tmp_path: Path):
    """Near-duplicate tickets (>0.85 cosine similarity) share a group and are never split across train/test."""
    # Create two nearly identical tickets and two distinct tickets
    t1 = _make_ticket(
        "NET-001",
        title="Tokyo office - whole network completely down",
        description="The entire Tokyo office network has died, wired and wifi both disconnected.",
    )
    t2 = _make_ticket(
        "NET-002",
        title="Tokyo office - whole network completely down",
        description="The entire Tokyo office network has died, wired and wifi both disconnected.",
    )
    t3 = _make_ticket(
        "HW-001",
        title="Laptop screen cracked",
        description="I accidentally dropped my backpack and the laptop LCD screen has multiple cracks.",
        category="hardware",
    )
    t4 = _make_ticket(
        "SW-001",
        title="Excel crashes on startup",
        description="Every time I double-click an Excel spreadsheet, Microsoft Office crashes with error code 0x800.",
        category="software",
    )

    tickets = [t1, t2, t3, t4]
    dups, group_mapping = compute_near_duplicates_and_groups(tickets, sim_threshold=0.85)

    assert len(dups) >= 1
    dup_ids = {dups[0][0], dups[0][1]}
    assert dup_ids == {"NET-001", "NET-002"}
    assert dups[0][2] > 0.85

    # Group IDs for t1 and t2 must be identical
    assert group_mapping["NET-001"] == group_mapping["NET-002"]
    # Distinct tickets must have their own groups
    assert group_mapping["HW-001"] != group_mapping["NET-001"]

    for t in tickets:
        t["group"] = group_mapping[t["id"]]

    # Run train/test split on tickets with groups
    train, test = split_train_test(tickets, train_ratio=0.5, seed=42)
    train_ids = {t["id"] for t in train}
    test_ids = {t["id"] for t in test}

    # Verify NET-001 and NET-002 never straddle the train/test split
    in_train = ("NET-001" in train_ids) and ("NET-002" in train_ids)
    in_test = ("NET-001" in test_ids) and ("NET-002" in test_ids)
    assert in_train or in_test, "Grouped near-duplicate tickets were split across train and test!"


def test_split_is_deterministic(tmp_path: Path):
    """The train/test split produces the exact same results with the same random seed."""
    tickets = [
        _make_ticket(f"T-{i:03d}", category="network" if i % 2 == 0 else "hardware", group=f"T-{i:03d}")
        for i in range(20)
    ]

    train1, test1 = split_train_test(tickets, train_ratio=0.8, seed=42)
    train2, test2 = split_train_test(tickets, train_ratio=0.8, seed=42)

    assert [t["id"] for t in train1] == [t["id"] for t in train2]
    assert [t["id"] for t in test1] == [t["id"] for t in test2]


def test_loader_text_excludes_label_note(tmp_path: Path):
    """load_split must construct text as title + '\n' + description and strictly omit label_note."""
    t = _make_ticket(
        "SEC-001",
        title="Password reset needed",
        description="Locked out after returning from leave.",
        label_note="CRITICAL GROUND TRUTH REASONING: DO NOT LEAK TO MODEL INPUT",
    )
    train_file = tmp_path / "train.jsonl"
    train_file.write_text(json.dumps(t) + "\n", encoding="utf-8")

    examples = load_split("train", data_dir=tmp_path)
    assert len(examples) == 1
    example = examples[0]

    assert isinstance(example, TicketExample)
    assert example.id == "SEC-001"
    assert example.text == "Password reset needed\nLocked out after returning from leave."
    assert "CRITICAL GROUND TRUTH REASONING" not in example.text
    assert "label_note" not in example.text
    assert not hasattr(example, "label_note")


def test_corrections_from_csv_are_applied(tmp_path: Path):
    """review_corrections.csv updates category and/or priority when provided."""
    tickets = [
        _make_ticket("CORR-001", category="software", priority="low"),
        _make_ticket("CORR-002", category="email", priority="medium"),
    ]

    corrections_file = tmp_path / "review_corrections.csv"
    with open(corrections_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "fix_category", "fix_priority"])
        # Update both category and priority on CORR-001
        writer.writerow(["CORR-001", "hardware", "urgent"])
        # Leave category blank on CORR-002, only update priority
        writer.writerow(["CORR-002", "", "high"])

    applied = apply_corrections_if_present(tickets, corrections_file)

    assert len(applied) == 3
    t1 = next(t for t in tickets if t["id"] == "CORR-001")
    t2 = next(t for t in tickets if t["id"] == "CORR-002")

    assert t1["category"] == "hardware"
    assert t1["priority"] == "urgent"
    assert t2["category"] == "email"  # Unchanged
    assert t2["priority"] == "high"    # Updated


def test_load_split_all_and_validation(tmp_path: Path):
    """load_split supports test and all, and validates split names."""
    t_train = _make_ticket("TR-001", title="Train title")
    t_test = _make_ticket("TE-001", title="Test title")

    (tmp_path / "train.jsonl").write_text(json.dumps(t_train) + "\n", encoding="utf-8")
    (tmp_path / "test.jsonl").write_text(json.dumps(t_test) + "\n", encoding="utf-8")

    test_examples = load_split("test", data_dir=tmp_path)
    assert len(test_examples) == 1
    assert test_examples[0].id == "TE-001"

    # Fallback to train + test when servicedesk600.jsonl not present
    all_examples = load_split("all", data_dir=tmp_path)
    assert len(all_examples) == 2
    assert {e.id for e in all_examples} == {"TR-001", "TE-001"}

    # When servicedesk600.jsonl exists
    t_all = _make_ticket("ALL-001", title="All title")
    (tmp_path / "servicedesk600.jsonl").write_text(json.dumps(t_all) + "\n", encoding="utf-8")
    assert len(load_split("all", data_dir=tmp_path)) == 1

    # Invalid split name
    with pytest.raises(ValueError, match="Invalid split name"):
        load_split("validation", data_dir=tmp_path)

    # Missing split file
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        load_split("train", data_dir=empty_dir)


def test_run_pipeline_end_to_end(tmp_path: Path):
    """run_pipeline completes successfully with all output artifacts created."""
    # Write a mini batch file
    batch = [
        json.dumps(_make_ticket(f"T-{i:03d}", category="network" if i % 2 == 0 else "software"))
        for i in range(10)
    ]
    (tmp_path / "batch_01.jsonl").write_text("\n".join(batch) + "\n", encoding="utf-8")

    results = run_pipeline(data_dir=tmp_path, seed=42)
    assert results["total_valid"] == 10
    assert results["total_rejected"] == 0
    assert (tmp_path / "servicedesk600.jsonl").is_file()
    assert (tmp_path / "train.jsonl").is_file()
    assert (tmp_path / "test.jsonl").is_file()
    assert (tmp_path / "rejected.jsonl").is_file()
    assert (tmp_path / "review_sample.csv").is_file()
    assert (tmp_path / "validation_report.md").is_file()

