"""
Build and validate the ServiceDesk500 dataset.

Loads 12 batch files, validates fields, detects near-duplicates with HashingEmbedder,
applies human review corrections (if present), creates group-aware stratified train/test
splits (80/20), generates a 10% review sample, and outputs a validation report.

Usage:
    python -m app.scripts.build_dataset [--data-dir PATH] [--seed INT]
"""

import argparse
import csv
import glob
import json
from pathlib import Path
import random
from typing import Any
import numpy as np

from app.ai.embedder import HashingEmbedder, get_text_to_embed


VALID_CATEGORIES = {"network", "hardware", "software", "access", "email", "other"}
VALID_PRIORITIES = {"low", "medium", "high", "urgent"}
VALID_DIFFICULTIES = {"easy", "hard"}
REQUIRED_FIELDS = ("id", "title", "description", "category", "priority", "difficulty", "label_note")

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "servicedesk500"


class DisjointSet:
    """Disjoint-set (Union-Find) data structure with path compression."""

    def __init__(self, items: list[str]) -> None:
        self.parent = {item: item for item in items}

    def find(self, item: str) -> str:
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, a: str, b: str) -> None:
        root_a = self.find(a)
        root_b = self.find(b)
        if root_a != root_b:
            # Deterministic: choose alphabetically smaller root
            if root_a < root_b:
                self.parent[root_b] = root_a
            else:
                self.parent[root_a] = root_b


def parse_batch_file(filepath: Path) -> list[tuple[int, str, dict[str, Any] | None, str | None]]:
    """
    Parse a JSONL batch file, supporting both single-line JSON objects and
    multi-line indented JSON objects where objects start with '{' and end with '}'.

    Returns:
        List of tuples: (line_number, raw_text, parsed_dict, parse_error_reason)
    """
    entries: list[tuple[int, str, dict[str, Any] | None, str | None]] = []
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i]
        line_str = line.strip()
        if not line_str:
            i += 1
            continue

        # 1. Multi-line indented JSON object: line is solely '{'
        if line_str == "{":
            start_line = i + 1
            buf = [line]
            i += 1
            matched = False
            while i < len(lines):
                buf.append(lines[i])
                if lines[i].strip() == "}":
                    matched = True
                    i += 1
                    break
                i += 1
            candidate = "".join(buf).strip()
            if matched:
                try:
                    parsed = json.loads(candidate)
                    if isinstance(parsed, dict):
                        entries.append((start_line, candidate, parsed, None))
                    else:
                        entries.append((start_line, candidate, None, "JSON root is not an object"))
                except Exception as exc:
                    entries.append((start_line, candidate, None, f"Invalid JSON: {exc}"))
            else:
                entries.append((start_line, candidate, None, "Unterminated multi-line JSON object"))
            continue

        # 2. Single-line entry
        try:
            parsed = json.loads(line_str)
            if isinstance(parsed, dict):
                entries.append((i + 1, line_str, parsed, None))
            else:
                entries.append((i + 1, line_str, None, "JSON root is not an object"))
        except Exception as exc:
            entries.append((i + 1, line_str, None, f"Invalid JSON: {exc}"))
        i += 1

    return entries


def load_and_validate_batches(
    data_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int], list[str]]:
    """
    Load all batch files, validate each line, and collect valid and rejected entries.
    """
    expected_batches = [f"batch_{idx:02d}.jsonl" for idx in range(1, 13)]
    missing_batches = [b for b in expected_batches if not (data_dir / b).is_file()]

    found_files = sorted(glob.glob(str(data_dir / "batch_*.jsonl")))
    
    seen_ids: dict[str, tuple[str, int]] = {}
    valid_tickets: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    batch_counts: dict[str, int] = {}

    for file_str in found_files:
        path = Path(file_str)
        fname = path.name
        entries = parse_batch_file(path)
        batch_valid_count = 0

        for line_num, raw_text, data, parse_err in entries:
            if parse_err is not None or data is None:
                rejected_rows.append({
                    "source_file": fname,
                    "line_number": line_num,
                    "raw": raw_text,
                    "reason": parse_err or "Invalid JSON",
                })
                continue

            reasons: list[str] = []

            # 1. Required fields check
            for field in REQUIRED_FIELDS:
                if field not in data or data[field] is None:
                    reasons.append(f"Missing field: '{field}'")
                elif isinstance(data[field], str) and not data[field].strip():
                    reasons.append(f"Empty field: '{field}'")

            # 2. Value domain checks
            if not reasons:
                cat = data.get("category")
                if cat not in VALID_CATEGORIES:
                    reasons.append(f"Invalid category '{cat}'. Allowed: {sorted(VALID_CATEGORIES)}")

                prio = data.get("priority")
                if prio not in VALID_PRIORITIES:
                    reasons.append(f"Invalid priority '{prio}'. Allowed: {sorted(VALID_PRIORITIES)}")

                diff = data.get("difficulty")
                if diff not in VALID_DIFFICULTIES:
                    reasons.append(f"Invalid difficulty '{diff}'. Allowed: {sorted(VALID_DIFFICULTIES)}")

                title = str(data.get("title", "")).strip()
                if len(title) < 3:
                    reasons.append(f"Title too short (< 3 chars): '{title}' (length {len(title)})")

                desc = str(data.get("description", "")).strip()
                if len(desc) < 10:
                    reasons.append(f"Description too short (< 10 chars): length {len(desc)}")

                ticket_id = str(data.get("id", "")).strip()
                if ticket_id in seen_ids:
                    orig_file, orig_line = seen_ids[ticket_id]
                    reasons.append(f"Duplicate id '{ticket_id}' (first seen in {orig_file}:{orig_line})")
                else:
                    seen_ids[ticket_id] = (fname, line_num)

            if reasons:
                rej_item = {
                    "source_file": fname,
                    "line_number": line_num,
                    "reason": "; ".join(reasons),
                }
                rej_item.update(data)
                rejected_rows.append(rej_item)
            else:
                valid_tickets.append(data)
                batch_valid_count += 1

        batch_counts[fname] = batch_valid_count

    return valid_tickets, rejected_rows, batch_counts, missing_batches


def compute_near_duplicates_and_groups(
    tickets: list[dict[str, Any]],
    sim_threshold: float = 0.85,
) -> tuple[list[tuple[str, str, float, str, str]], dict[str, str]]:
    """
    Compute pairwise cosine similarity using HashingEmbedder on title + description.
    Pairs above sim_threshold are placed in the same group via connected components.
    All other tickets get their own group ID.
    """
    if not tickets:
        return [], {}

    embedder = HashingEmbedder()
    texts = [get_text_to_embed(t["title"], t["description"]) for t in tickets]
    vectors = np.array(embedder.embed(texts), dtype=np.float32)

    # Unit vectors => cosine similarity is dot product
    sim_matrix = vectors @ vectors.T

    n = len(tickets)
    ticket_ids = [t["id"] for t in tickets]
    dset = DisjointSet(ticket_ids)
    duplicate_pairs: list[tuple[str, str, float, str, str]] = []

    for i in range(n):
        for j in range(i + 1, n):
            score = float(sim_matrix[i, j])
            if score > sim_threshold:
                id_i = tickets[i]["id"]
                id_j = tickets[j]["id"]
                duplicate_pairs.append((
                    id_i,
                    id_j,
                    score,
                    tickets[i]["title"],
                    tickets[j]["title"],
                ))
                dset.union(id_i, id_j)

    # Map each ticket to group ID
    # For connected components with >1 ticket: 'grp_{canonical_id}'
    # For standalone tickets: their own id
    component_members: dict[str, list[str]] = {}
    for tid in ticket_ids:
        root = dset.find(tid)
        component_members.setdefault(root, []).append(tid)

    group_mapping: dict[str, str] = {}
    for root, members in component_members.items():
        if len(members) > 1:
            canonical = sorted(members)[0]
            group_name = f"grp_{canonical}"
            for member in members:
                group_mapping[member] = group_name
        else:
            group_mapping[members[0]] = members[0]

    return duplicate_pairs, group_mapping


def apply_corrections_if_present(
    tickets: list[dict[str, Any]],
    corrections_file: Path,
) -> list[dict[str, Any]]:
    """
    Apply category and priority corrections from review_corrections.csv if it exists.
    """
    applied_corrections: list[dict[str, Any]] = []
    if not corrections_file.is_file():
        return applied_corrections

    ticket_by_id = {t["id"]: t for t in tickets}

    with open(corrections_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tid = row.get("id", "").strip()
            if not tid or tid not in ticket_by_id:
                continue

            ticket = ticket_by_id[tid]
            fix_cat = row.get("fix_category", "").strip()
            fix_prio = row.get("fix_priority", "").strip()

            if fix_cat and fix_cat in VALID_CATEGORIES and fix_cat != ticket["category"]:
                old_cat = ticket["category"]
                ticket["category"] = fix_cat
                applied_corrections.append({
                    "id": tid,
                    "field": "category",
                    "old_value": old_cat,
                    "new_value": fix_cat,
                })

            if fix_prio and fix_prio in VALID_PRIORITIES and fix_prio != ticket["priority"]:
                old_prio = ticket["priority"]
                ticket["priority"] = fix_prio
                applied_corrections.append({
                    "id": tid,
                    "field": "priority",
                    "old_value": old_prio,
                    "new_value": fix_prio,
                })

    return applied_corrections


def split_train_test(
    tickets: list[dict[str, Any]],
    train_ratio: float = 0.80,
    seed: int = 42,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Group-aware, deterministic split stratified by (category, difficulty).
    Whole groups are assigned strictly to train or test.
    """
    rng = random.Random(seed)

    # 1. Aggregate tickets by group
    groups: dict[str, list[dict[str, Any]]] = {}
    for t in tickets:
        grp = t["group"]
        groups.setdefault(grp, []).append(t)

    # 2. Determine primary stratum for each group: (category, difficulty)
    strata: dict[tuple[str, str], list[tuple[str, list[dict[str, Any]]]]] = {}
    for grp, grp_tickets in sorted(groups.items()):
        # Majority category and difficulty
        cats = [t["category"] for t in grp_tickets]
        diffs = [t["difficulty"] for t in grp_tickets]
        prim_cat = max(set(cats), key=cats.count)
        prim_diff = max(set(diffs), key=diffs.count)
        strata.setdefault((prim_cat, prim_diff), []).append((grp, grp_tickets))

    train_tickets: list[dict[str, Any]] = []
    test_tickets: list[dict[str, Any]] = []

    # 3. For each stratum, allocate groups deterministically
    for (cat, diff), group_list in sorted(strata.items()):
        # Deterministic shuffle of groups in this stratum
        group_list_shuffled = list(group_list)
        # Sort by group ID first for reproducible seed ordering
        group_list_shuffled.sort(key=lambda item: item[0])
        rng.shuffle(group_list_shuffled)

        stratum_total_tickets = sum(len(items) for _, items in group_list_shuffled)
        target_test = round((1.0 - train_ratio) * stratum_total_tickets)

        current_test = 0
        stratum_train: list[dict[str, Any]] = []
        stratum_test: list[dict[str, Any]] = []

        for grp_id, items in group_list_shuffled:
            n_items = len(items)
            # Allocate to test if we have room and haven't reached target
            if current_test + n_items <= target_test and target_test > 0:
                stratum_test.extend(items)
                current_test += n_items
            else:
                stratum_train.extend(items)

        train_tickets.extend(stratum_train)
        test_tickets.extend(stratum_test)

    # Sort deterministically by id
    train_tickets.sort(key=lambda t: t["id"])
    test_tickets.sort(key=lambda t: t["id"])

    return train_tickets, test_tickets


def generate_review_sample(
    tickets: list[dict[str, Any]],
    sample_ratio: float = 0.10,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """
    Select a deterministic sample (10%) stratified by category for human review.
    """
    rng = random.Random(seed)
    by_category: dict[str, list[dict[str, Any]]] = {}
    for t in tickets:
        by_category.setdefault(t["category"], []).append(t)

    sampled: list[dict[str, Any]] = []
    for cat in sorted(by_category.keys()):
        cat_tickets = sorted(by_category[cat], key=lambda t: t["id"])
        rng.shuffle(cat_tickets)
        k = round(len(cat_tickets) * sample_ratio)
        sampled.extend(cat_tickets[:k])

    sampled.sort(key=lambda t: t["id"])
    return sampled


def build_markdown_report(
    batch_counts: dict[str, int],
    missing_batches: list[str],
    rejected_rows: list[dict[str, Any]],
    near_dups: list[tuple[str, str, float, str, str]],
    corrections: list[dict[str, Any]],
    all_tickets: list[dict[str, Any]],
    train_tickets: list[dict[str, Any]],
    test_tickets: list[dict[str, Any]],
) -> str:
    """Generate comprehensive validation_report.md."""

    def count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
        c: dict[str, int] = {}
        for item in items:
            val = str(item.get(key, ""))
            c[val] = c.get(val, 0) + 1
        return c

    all_cats = count_by(all_tickets, "category")
    train_cats = count_by(train_tickets, "category")
    test_cats = count_by(test_tickets, "category")

    all_prios = count_by(all_tickets, "priority")
    train_prios = count_by(train_tickets, "priority")
    test_prios = count_by(test_tickets, "priority")

    all_diffs = count_by(all_tickets, "difficulty")
    train_diffs = count_by(train_tickets, "difficulty")
    test_diffs = count_by(test_tickets, "difficulty")

    lines: list[str] = []
    lines.append("# ServiceDesk500 Validation Report")
    lines.append("")
    lines.append(f"**Execution command:** `python -m app.scripts.build_dataset`")
    lines.append("")
    lines.append("## 1. Batch Loading Summary")
    lines.append("")
    lines.append("| Batch File | Valid Tickets Loaded | Status |")
    lines.append("| :--- | :--- | :--- |")
    for bname in sorted(batch_counts.keys()):
        lines.append(f"| `{bname}` | {batch_counts[bname]} | Valid |")
    if missing_batches:
        for mb in missing_batches:
            lines.append(f"| `{mb}` | 0 | **Missing** |")
    lines.append("")
    lines.append(f"- **Total valid tickets loaded:** {len(all_tickets)}")
    lines.append(f"- **Total rejected rows:** {len(rejected_rows)}")
    lines.append("")

    lines.append("## 2. Rejected Rows")
    lines.append("")
    if not rejected_rows:
        lines.append("No rows were rejected. All batch files passed schema and domain validation.")
    else:
        lines.append(f"Total rejected: {len(rejected_rows)}")
        lines.append("")
        lines.append("| Source File | Line | Reason | Ticket ID |")
        lines.append("| :--- | :--- | :--- | :--- |")
        for r in rejected_rows:
            tid = r.get("id", "N/A")
            lines.append(f"| `{r['source_file']}` | {r['line_number']} | {r['reason']} | `{tid}` |")
    lines.append("")

    lines.append("## 3. Near-Duplicate Pairs (Cosine Similarity > 0.85)")
    lines.append("")
    lines.append(f"Evaluated pairwise similarity using `HashingEmbedder` (`hashing-v2`, 4096 dimensions).")
    lines.append(f"Pairs found above threshold (0.85): **{len(near_dups)}**")
    lines.append("")
    if not near_dups:
        lines.append("No near-duplicate pairs above 0.85 cosine similarity were found in the dataset.")
    else:
        lines.append("| Ticket A | Ticket B | Cosine Similarity | Title A | Title B |")
        lines.append("| :--- | :--- | :--- | :--- | :--- |")
        for p in near_dups:
            lines.append(f"| `{p[0]}` | `{p[1]}` | {p[2]:.4f} | {p[3]} | {p[4]} |")
    lines.append("")

    lines.append("## 4. Human Review Corrections Applied")
    lines.append("")
    if not corrections:
        lines.append("No review corrections applied (either `review_corrections.csv` was absent or contained no updates).")
    else:
        lines.append("| Ticket ID | Field | Old Value | Corrected Value |")
        lines.append("| :--- | :--- | :--- | :--- |")
        for c in corrections:
            lines.append(f"| `{c['id']}` | `{c['field']}` | `{c['old_value']}` | `{c['new_value']}` |")
    lines.append("")

    lines.append("## 5. Train / Test Split Tables (80% Train / 20% Test, Seed 42)")
    lines.append("")
    lines.append("### Category Distribution")
    lines.append("")
    lines.append("| Category | Total | Train | Test | Train % | Test % |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for cat in sorted(VALID_CATEGORIES):
        tot = all_cats.get(cat, 0)
        tr = train_cats.get(cat, 0)
        te = test_cats.get(cat, 0)
        tr_pct = f"{(tr / tot * 100):.1f}%" if tot else "0.0%"
        te_pct = f"{(te / tot * 100):.1f}%" if tot else "0.0%"
        lines.append(f"| `{cat}` | {tot} | {tr} | {te} | {tr_pct} | {te_pct} |")
    lines.append(f"| **Total** | **{len(all_tickets)}** | **{len(train_tickets)}** | **{len(test_tickets)}** | **{(len(train_tickets)/len(all_tickets)*100):.1f}%** | **{(len(test_tickets)/len(all_tickets)*100):.1f}%** |")
    lines.append("")

    lines.append("### Priority Distribution")
    lines.append("")
    lines.append("| Priority | Total | Train | Test | Train % | Test % |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for prio in ["low", "medium", "high", "urgent"]:
        tot = all_prios.get(prio, 0)
        tr = train_prios.get(prio, 0)
        te = test_prios.get(prio, 0)
        tr_pct = f"{(tr / tot * 100):.1f}%" if tot else "0.0%"
        te_pct = f"{(te / tot * 100):.1f}%" if tot else "0.0%"
        lines.append(f"| `{prio}` | {tot} | {tr} | {te} | {tr_pct} | {te_pct} |")
    lines.append(f"| **Total** | **{len(all_tickets)}** | **{len(train_tickets)}** | **{len(test_tickets)}** | **{(len(train_tickets)/len(all_tickets)*100):.1f}%** | **{(len(test_tickets)/len(all_tickets)*100):.1f}%** |")
    lines.append("")

    lines.append("### Difficulty Distribution")
    lines.append("")
    lines.append("| Difficulty | Total | Train | Test | Train % | Test % |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for diff in ["easy", "hard"]:
        tot = all_diffs.get(diff, 0)
        tr = train_diffs.get(diff, 0)
        te = test_diffs.get(diff, 0)
        tr_pct = f"{(tr / tot * 100):.1f}%" if tot else "0.0%"
        te_pct = f"{(te / tot * 100):.1f}%" if tot else "0.0%"
        lines.append(f"| `{diff}` | {tot} | {tr} | {te} | {tr_pct} | {te_pct} |")
    lines.append(f"| **Total** | **{len(all_tickets)}** | **{len(train_tickets)}** | **{len(test_tickets)}** | **{(len(train_tickets)/len(all_tickets)*100):.1f}%** | **{(len(test_tickets)/len(all_tickets)*100):.1f}%** |")
    lines.append("")

    return "\n".join(lines) + "\n"


def run_pipeline(
    data_dir: Path,
    seed: int = 42,
    sim_threshold: float = 0.85,
    train_ratio: float = 0.80,
    sample_ratio: float = 0.10,
) -> dict[str, Any]:
    """Execute the full dataset creation pipeline."""
    # 1. Load and validate
    tickets, rejected_rows, batch_counts, missing_batches = load_and_validate_batches(data_dir)

    # 2. Write rejected.jsonl
    rejected_file = data_dir / "rejected.jsonl"
    with open(rejected_file, "w", encoding="utf-8") as f:
        for r in rejected_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 3. Near-duplicate detection & grouping
    near_dups, group_mapping = compute_near_duplicates_and_groups(tickets, sim_threshold=sim_threshold)
    for t in tickets:
        t["group"] = group_mapping.get(t["id"], t["id"])

    # 4. Review corrections
    corrections_file = data_dir / "review_corrections.csv"
    corrections_applied = apply_corrections_if_present(tickets, corrections_file)

    # 5. Write merged file
    merged_file = data_dir / "servicedesk500.jsonl"
    with open(merged_file, "w", encoding="utf-8") as f:
        for t in tickets:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

    # 6. Train/Test split
    train_tickets, test_tickets = split_train_test(tickets, train_ratio=train_ratio, seed=seed)
    with open(data_dir / "train.jsonl", "w", encoding="utf-8") as f:
        for t in train_tickets:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

    with open(data_dir / "test.jsonl", "w", encoding="utf-8") as f:
        for t in test_tickets:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

    # 7. Write review_sample.csv
    sample_tickets = generate_review_sample(tickets, sample_ratio=sample_ratio, seed=seed)
    sample_file = data_dir / "review_sample.csv"
    sample_fields = [
        "id", "title", "description", "category", "priority", "difficulty", "label_note", "fix_category", "fix_priority"
    ]
    with open(sample_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=sample_fields)
        writer.writeheader()
        for t in sample_tickets:
            row = {k: t.get(k, "") for k in sample_fields}
            row["fix_category"] = ""
            row["fix_priority"] = ""
            writer.writerow(row)

    # 8. Write validation_report.md
    report_content = build_markdown_report(
        batch_counts=batch_counts,
        missing_batches=missing_batches,
        rejected_rows=rejected_rows,
        near_dups=near_dups,
        corrections=corrections_applied,
        all_tickets=tickets,
        train_tickets=train_tickets,
        test_tickets=test_tickets,
    )
    with open(data_dir / "validation_report.md", "w", encoding="utf-8") as f:
        f.write(report_content)

    return {
        "total_valid": len(tickets),
        "total_rejected": len(rejected_rows),
        "train_count": len(train_tickets),
        "test_count": len(test_tickets),
        "sample_count": len(sample_tickets),
        "near_duplicate_pairs": near_dups,
        "corrections_applied": corrections_applied,
        "batch_counts": batch_counts,
        "missing_batches": missing_batches,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and validate ServiceDesk500 dataset.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="Path to data directory")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for splitting and sampling")
    parser.add_argument("--sim-threshold", type=float, default=0.85, help="Cosine similarity duplicate threshold")
    args = parser.parse_args()

    results = run_pipeline(
        data_dir=args.data_dir,
        seed=args.seed,
        sim_threshold=args.sim_threshold,
    )

    print(f"Dataset build complete.")
    print(f"  Valid tickets:   {results['total_valid']}")
    print(f"  Rejected rows:   {results['total_rejected']}")
    print(f"  Train split:     {results['train_count']}")
    print(f"  Test split:      {results['test_count']}")
    print(f"  Review sample:   {results['sample_count']}")
    print(f"  Near-dup pairs:  {len(results['near_duplicate_pairs'])}")
    print(f"  Corrections:     {len(results['corrections_applied'])}")


if __name__ == "__main__":
    main()
