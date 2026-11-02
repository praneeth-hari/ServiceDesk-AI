"""
Evaluate AI triage category and priority prediction on synthetic benchmark dataset.

Usage:
    python -m app.scripts.eval_triage [--embedder hashing|sbert] [--k 5] [--min-sim 0.12] [--tune]
"""
import argparse
from collections import Counter, defaultdict
import csv
from pathlib import Path
import sys
from typing import Any
import numpy as np
from sklearn.model_selection import StratifiedKFold, train_test_split

from app.ai.embedder import Embedder, get_embedder, get_text_to_embed
from app.core.config import settings
from app.models.enums import TicketCategory, TicketPriority
from app.services.triage import predict_knn


def load_dataset(csv_path: Path) -> list[dict[str, str]]:
    """Load tickets from CSV skipping comment lines."""
    rows = []
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for line in reader:
            if not line or line[0].startswith("#"):
                continue
            if line[0].strip().lower() == "title":
                # Header row
                continue
            if len(line) >= 4:
                rows.append(
                    {
                        "title": line[0].strip(),
                        "description": line[1].strip(),
                        "category": line[2].strip().lower(),
                        "priority": line[3].strip().lower(),
                    }
                )
    return rows


def run_cross_validation_tuning(
    train_data: list[dict[str, str]],
    embedder: Embedder,
    k: int = 5,
    random_state: int = 42,
    sim_thresholds: list[float] | None = None,
) -> list[dict[str, Any]]:
    """
    Run 5-fold stratified cross-validation on the TRAIN split only.
    Tests min_similarity values to select the optimal operating threshold.
    """
    if sim_thresholds is None:
        sim_thresholds = [0.05, 0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 0.25, 0.30, 0.35, 0.40]

    train_categories = [r["category"] for r in train_data]
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=random_state)

    print("\n" + "=" * 80)
    print("5-FOLD CROSS-VALIDATION TUNING ON TRAIN SPLIT ONLY (N=96)")
    print("=" * 80)
    print(
        f"{'min_sim':<8} | {'Coverage':<10} | {'Acc (when made)':<18} "
        f"| {'Overall Acc (inc No Sugg)':<26} | {'Priority Overall':<16}"
    )
    print("-" * 88)

    # Pre-embed all train data to avoid redundant computations across threshold sweeps
    train_texts = [get_text_to_embed(r["title"], r["description"]) for r in train_data]
    all_train_vecs = np.vstack(embedder.embed(train_texts)).astype(np.float32)

    tuning_results = []

    # Map fold indices
    folds = list(skf.split(train_data, train_categories))

    for min_sim in sim_thresholds:
        fold_coverages = []
        fold_acc_suggested = []
        fold_acc_overall = []
        fold_prio_overall = []

        for train_idx, val_idx in folds:
            fold_train = [train_data[i] for i in train_idx]
            fold_val = [train_data[i] for i in val_idx]

            f_train_vecs = all_train_vecs[train_idx]
            f_val_vecs = all_train_vecs[val_idx]

            n_suggested = 0
            n_cat_correct = 0
            n_prio_correct = 0

            for vi, val_row in enumerate(fold_val):
                sims = np.dot(f_train_vecs, f_val_vecs[vi])
                candidates = [
                    {
                        "category": TicketCategory(fold_train[ti]["category"]),
                        "priority": TicketPriority(fold_train[ti]["priority"]),
                        "similarity": float(sims[ti]),
                    }
                    for ti in range(len(fold_train))
                ]

                pred_cat, pred_prio, _ = predict_knn(candidates, k=k, min_similarity=min_sim)
                if pred_cat is not None:
                    n_suggested += 1
                    if pred_cat.value == val_row["category"]:
                        n_cat_correct += 1
                    if pred_prio and pred_prio.value == val_row["priority"]:
                        n_prio_correct += 1

            total_val = len(fold_val)
            cov = n_suggested / total_val if total_val else 0.0
            acc_sugg = (n_cat_correct / n_suggested) if n_suggested > 0 else 0.0
            acc_over = n_cat_correct / total_val if total_val else 0.0
            prio_over = n_prio_correct / total_val if total_val else 0.0

            fold_coverages.append(cov)
            fold_acc_suggested.append(acc_sugg)
            fold_acc_overall.append(acc_over)
            fold_prio_overall.append(prio_over)

        mean_cov = float(np.mean(fold_coverages))
        mean_acc_sugg = float(np.mean(fold_acc_suggested))
        mean_acc_over = float(np.mean(fold_acc_overall))
        mean_prio_over = float(np.mean(fold_prio_overall))

        print(
            f"{min_sim:<8.2f} | {mean_cov * 100:6.1f}%   | {mean_acc_sugg * 100:6.1f}%           "
            f"| {mean_acc_over * 100:6.1f}%                    | {mean_prio_over * 100:6.1f}%"
        )

        tuning_results.append(
            {
                "min_sim": min_sim,
                "coverage": mean_cov,
                "acc_when_suggested": mean_acc_sugg,
                "overall_accuracy": mean_acc_over,
                "priority_overall": mean_prio_over,
            }
        )

    print("=" * 88)
    return tuning_results


def run_evaluation(
    embedder_name: str = "hashing",
    k: int = 5,
    min_similarity: float = 0.12,
    random_state: int = 42,
    csv_path: Path = Path("data") / "triage_eval.csv",
    tune: bool = False,
) -> dict[str, Any]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Evaluation dataset not found at {csv_path}")

    # 1. Load Embedder
    try:
        embedder = get_embedder(embedder_name)
    except (ImportError, ValueError) as exc:
        print(f"\n[Error] Failed to load embedder '{embedder_name}': {exc}", file=sys.stderr)
        sys.exit(1)

    dataset = load_dataset(csv_path)
    if not dataset:
        raise ValueError(f"No records found in dataset {csv_path}")

    # 2. Seeded 80/20 train/test split stratified by category
    categories = [row["category"] for row in dataset]
    train_data, test_data = train_test_split(
        dataset,
        test_size=0.20,
        random_state=random_state,
        stratify=categories,
    )

    tuning_table = None
    if tune:
        tuning_table = run_cross_validation_tuning(
            train_data=train_data,
            embedder=embedder,
            k=k,
            random_state=random_state,
        )

    print(
        f"\nEvaluating AI Triage on Test Split ({len(test_data)} tickets, pool={len(train_data)} train tickets) "
        f"using embedder '{embedder.name}' (dim={embedder.dim}, k={k}, min_similarity={min_similarity})..."
    )

    # 3. Build in-memory neighbour index from train set
    train_texts = [get_text_to_embed(r["title"], r["description"]) for r in train_data]
    train_vectors = embedder.embed(train_texts)
    train_matrix = np.vstack(train_vectors).astype(np.float32)

    # 4. Predict on test set
    test_texts = [get_text_to_embed(r["title"], r["description"]) for r in test_data]
    test_vectors = embedder.embed(test_texts)

    cat_correct = 0
    prio_correct = 0
    n_suggested = 0

    per_cat_total: dict[str, int] = defaultdict(int)
    per_cat_correct: dict[str, int] = defaultdict(int)

    for i, test_row in enumerate(test_data):
        test_vec = test_vectors[i].astype(np.float32)
        # Cosine similarity dot product against train matrix
        sims = np.dot(train_matrix, test_vec)

        candidates = []
        for j, train_row in enumerate(train_data):
            candidates.append(
                {
                    "category": TicketCategory(train_row["category"]),
                    "priority": TicketPriority(train_row["priority"]),
                    "similarity": float(sims[j]),
                }
            )

        pred_cat, pred_prio, conf = predict_knn(
            candidates,
            k=k,
            min_similarity=min_similarity,
        )

        true_cat = test_row["category"]
        true_prio = test_row["priority"]
        per_cat_total[true_cat] += 1

        if pred_cat is not None:
            n_suggested += 1
            if pred_cat.value == true_cat:
                cat_correct += 1
                per_cat_correct[true_cat] += 1
            if pred_prio and pred_prio.value == true_prio:
                prio_correct += 1

    total_test = len(test_data)
    no_suggestion_count = total_test - n_suggested
    coverage = (n_suggested / total_test) if total_test else 0.0
    cat_accuracy_overall = (cat_correct / total_test) if total_test else 0.0
    cat_accuracy_when_made = (cat_correct / n_suggested) if n_suggested else 0.0
    prio_accuracy_overall = (prio_correct / total_test) if total_test else 0.0
    prio_accuracy_when_made = (prio_correct / n_suggested) if n_suggested else 0.0

    # Baselines
    dataset_cat_counts = Counter(r["category"] for r in dataset)
    majority_cat_count = max(dataset_cat_counts.values()) if dataset_cat_counts else 0
    majority_cat_baseline = majority_cat_count / len(dataset) if dataset else 0.0
    random_chance_cat_baseline = 1.0 / len(dataset_cat_counts) if dataset_cat_counts else 0.0

    dataset_prio_counts = Counter(r["priority"] for r in dataset)
    majority_prio_count = max(dataset_prio_counts.values()) if dataset_prio_counts else 0
    majority_prio_baseline = majority_prio_count / len(dataset) if dataset else 0.0
    random_chance_prio_baseline = 1.0 / len(dataset_prio_counts) if dataset_prio_counts else 0.0

    print("\n" + "=" * 65)
    print(f"AI TRIAGE EVALUATION REPORT (MODEL: {embedder.name.upper()})")
    print("=" * 65)
    print(f"Total Test Set Samples   : {total_test}")
    print(f"Suggestions Made         : {n_suggested} ({coverage * 100:.2f}% coverage)")
    print(f"No Suggestion Count      : {no_suggestion_count} ({(1 - coverage) * 100:.2f}%)")
    print("-" * 65)
    print("CATEGORY PREDICTION METRICS:")
    print(f"  - Overall Accuracy     : {cat_accuracy_overall * 100:.2f}% ({cat_correct}/{total_test}) [no-suggestion = wrong]")
    print(f"  - Acc When Suggested   : {cat_accuracy_when_made * 100:.2f}% ({cat_correct}/{n_suggested})")
    print(f"  - Majority Baseline    : {majority_cat_baseline * 100:.2f}% (balanced dataset: 20/120)")
    print(f"  - Random Chance        : {random_chance_cat_baseline * 100:.2f}% (1 of {len(dataset_cat_counts)} categories)")
    print("-" * 65)
    print("PRIORITY PREDICTION METRICS:")
    print(f"  - Overall Accuracy     : {prio_accuracy_overall * 100:.2f}% ({prio_correct}/{total_test})")
    print(f"  - Acc When Suggested   : {prio_accuracy_when_made * 100:.2f}% ({prio_correct}/{n_suggested})")
    print(f"  - Majority Baseline    : {majority_prio_baseline * 100:.2f}%")
    print(f"  - Random Chance        : {random_chance_prio_baseline * 100:.2f}% (1 of {len(dataset_prio_counts)} priorities)")
    print("-" * 65)
    print("PER-CATEGORY ACCURACY BREAKDOWN:")
    for cat in sorted(per_cat_total.keys()):
        tot = per_cat_total[cat]
        cor = per_cat_correct[cat]
        acc = (cor / tot * 100) if tot else 0.0
        print(f"  - {cat:<12}: {acc:6.2f}% ({cor}/{tot})")
    print("-" * 65)

    if cat_accuracy_overall < 0.60:
        print(
            "NOTE: Overall category accuracy is below 60%.\n"
            "Key drivers:\n"
            "1. Small corpus (96 train tickets across 6 categories = 16 tickets/category).\n"
            "2. Semantic overlap in IT ticket vocabulary (e.g., 'backup', 'access', 'network share'\n"
            "   span Hardware, Network, and Access categories).\n"
            "3. Deterministic n-gram hashing lacks deep contextual embeddings.\n"
            "Priority is inherently more subjective than category across users and tickets."
        )
    print("=" * 65 + "\n")

    return {
        "embedder": embedder.name,
        "dim": embedder.dim,
        "total_test": total_test,
        "suggestions_made": n_suggested,
        "coverage": coverage,
        "no_suggestion_count": no_suggestion_count,
        "overall_category_accuracy": cat_accuracy_overall,
        "category_accuracy_when_made": cat_accuracy_when_made,
        "majority_category_baseline": majority_cat_baseline,
        "random_chance_category_baseline": random_chance_cat_baseline,
        "overall_priority_accuracy": prio_accuracy_overall,
        "priority_accuracy_when_made": prio_accuracy_when_made,
        "majority_priority_baseline": majority_prio_baseline,
        "random_chance_priority_baseline": random_chance_prio_baseline,
        "per_category_accuracy": {
            cat: (per_cat_correct[cat] / per_cat_total[cat]) if per_cat_total[cat] else 0.0
            for cat in per_cat_total
        },
        "tuning_results": tuning_table,
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate IT helpdesk AI triage accuracy")
    parser.add_argument(
        "--embedder",
        choices=["hashing", "hashing-v2", "sbert"],
        default=settings.AI_EMBEDDER,
        help="Embedding model backend (default: from settings)",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=settings.AI_KNN_K,
        help="Top-k neighbours to consider (default: from settings)",
    )
    parser.add_argument(
        "--min-sim",
        type=float,
        default=settings.AI_MIN_SIMILARITY,
        help="Minimum similarity threshold (default: from settings)",
    )
    parser.add_argument(
        "--tune",
        action="store_true",
        help="Run 5-fold cross-validation on train split only across similarity thresholds",
    )
    args = parser.parse_args()

    run_evaluation(
        embedder_name=args.embedder,
        k=args.k,
        min_similarity=args.min_sim,
        tune=args.tune,
    )


if __name__ == "__main__":
    main()
