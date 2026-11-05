"""
Prefix variant selection for Ollama nomic-embed-text via 5-fold cross-validation
on data/servicedesk600/train.jsonl ONLY (N=480). Strictly does not touch test.jsonl.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import time
from typing import Any

import numpy as np
from sklearn.model_selection import KFold

from app.ai.dataset import load_split
from app.ai.embedder import OllamaEmbedder
from app.ai.llm_triage import CATEGORIES
from app.models.enums import TicketCategory, TicketPriority
from app.scripts.benchmark_triage import compute_macro_f1, compute_wilson_ci
from app.services.triage import predict_knn

PRIORITY_RANKS = {"low": 0, "medium": 1, "high": 2, "urgent": 3}

CANDIDATES = [
    {
        "variant": "search",
        "doc_prefix": "search_document: ",
        "query_prefix": "search_query: ",
        "description": "Asymmetric search (document for stored, query for lookup)",
    },
    {
        "variant": "classification",
        "doc_prefix": "classification: ",
        "query_prefix": "classification: ",
        "description": "Symmetric classification prefix for both stored and query",
    },
    {
        "variant": "clustering",
        "doc_prefix": "clustering: ",
        "query_prefix": "clustering: ",
        "description": "Symmetric clustering prefix for both stored and query",
    },
    {
        "variant": "none",
        "doc_prefix": "",
        "query_prefix": "",
        "description": "No task prefix (raw ticket text)",
    },
]


def run_cv_for_variant(
    candidate: dict[str, str],
    train_tickets: list[Any],
    folds: list[tuple[np.ndarray, np.ndarray]],
    embedder: OllamaEmbedder,
    k: int = 5,
    min_similarity: float = 0.12,
) -> dict[str, Any]:
    variant_name = candidate["variant"]
    doc_prefix = candidate["doc_prefix"]
    query_prefix = candidate["query_prefix"]

    train_texts = [t.text for t in train_tickets]
    print(f"\n--- Embedding train set for variant: '{variant_name}' ---")
    t0 = time.time()

    # Pre-embed with doc_prefix (for stored items) and query_prefix (for query items)
    stored_vecs = np.vstack(embedder.embed(train_texts, prefix=doc_prefix)).astype(np.float32)
    if query_prefix == doc_prefix:
        query_vecs = stored_vecs
    else:
        query_vecs = np.vstack(embedder.embed(train_texts, prefix=query_prefix)).astype(np.float32)

    embed_time = time.time() - t0
    print(f"[{variant_name}] Vectors ready in {embed_time:.2f}s (stored={stored_vecs.shape}, query={query_vecs.shape})")

    # Evaluate across 5 folds
    cat_correct = 0
    prio_correct = 0
    prio_within_one = 0
    combined_correct = 0
    all_true_cat = []
    all_pred_cat = []
    predictions = []

    for fold_idx, (train_idx, val_idx) in enumerate(folds):
        fold_stored_vecs = stored_vecs[train_idx]
        fold_stored_tickets = [train_tickets[i] for i in train_idx]

        for q_idx in val_idx:
            q_ticket = train_tickets[q_idx]
            q_vec = query_vecs[q_idx]

            sims = np.dot(fold_stored_vecs, q_vec)
            candidates = [
                {
                    "category": TicketCategory(fold_stored_tickets[j].category),
                    "priority": TicketPriority(fold_stored_tickets[j].priority),
                    "similarity": float(sims[j]),
                }
                for j in range(len(fold_stored_tickets))
            ]

            pred_cat, pred_prio, conf = predict_knn(
                candidates,
                k=k,
                min_similarity=min_similarity,
            )

            p_cat_val = pred_cat.value if pred_cat else None
            p_prio_val = pred_prio.value if pred_prio else None

            is_cat = (p_cat_val == q_ticket.category)
            is_prio = (p_prio_val == q_ticket.priority)
            true_prio_rank = PRIORITY_RANKS.get(q_ticket.priority, 1)
            pred_prio_rank = PRIORITY_RANKS.get(p_prio_val, -99) if p_prio_val else -99
            is_w1 = abs(true_prio_rank - pred_prio_rank) <= 1

            if is_cat:
                cat_correct += 1
            if is_prio:
                prio_correct += 1
            if is_w1:
                prio_within_one += 1
            if is_cat and is_prio:
                combined_correct += 1

            all_true_cat.append(q_ticket.category)
            all_pred_cat.append(p_cat_val or "none")

            predictions.append({
                "id": q_ticket.id,
                "fold": fold_idx,
                "true_category": q_ticket.category,
                "predicted_category": p_cat_val,
                "true_priority": q_ticket.priority,
                "predicted_priority": p_prio_val,
                "category_correct": is_cat,
                "priority_correct": is_prio,
            })

    n = len(train_tickets)
    cat_acc = round(cat_correct / n, 4)
    cat_ci = compute_wilson_ci(cat_correct, n)
    prio_acc = round(prio_correct / n, 4)
    prio_ci = compute_wilson_ci(prio_correct, n)
    w1_acc = round(prio_within_one / n, 4)
    comb_acc = round(combined_correct / n, 4)
    comb_ci = compute_wilson_ci(combined_correct, n)
    macro_f1_val, _ = compute_macro_f1(all_true_cat, all_pred_cat, CATEGORIES)
    macro_f1 = round(macro_f1_val, 4)

    return {
        "variant": variant_name,
        "doc_prefix": doc_prefix,
        "query_prefix": query_prefix,
        "description": candidate["description"],
        "n_samples": n,
        "n_folds": len(folds),
        "k": k,
        "category_accuracy": cat_acc,
        "category_ci": cat_ci,
        "macro_f1": macro_f1,
        "priority_accuracy": prio_acc,
        "priority_ci": prio_ci,
        "priority_within_one": w1_acc,
        "combined_accuracy": comb_acc,
        "combined_ci": comb_ci,
        "predictions": predictions,
    }


def main():
    parser = argparse.ArgumentParser(description="Select nomic-embed-text prefix variant via CV on train set.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("benchmarks") / "results_retrieval",
        help="Directory to save variant selection results.",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    print("Loading data/servicedesk600/train.jsonl (Strictly ignoring test.jsonl)...")
    train_tickets = load_split("train")
    assert len(train_tickets) == 480, f"Expected 480 training tickets, got {len(train_tickets)}"

    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    folds = list(kf.split(train_tickets))

    embedder = OllamaEmbedder()
    print(f"Ollama nomic-embed-text digest: {embedder.digest}")
    print(f"Ollama server version: {embedder.version}")

    results = []
    for cand in CANDIDATES:
        res = run_cv_for_variant(cand, train_tickets, folds, embedder)
        results.append(res)

    # Sort results by Category Accuracy descending, then Priority Accuracy descending
    results.sort(key=lambda x: (x["category_accuracy"], x["priority_accuracy"]), reverse=True)

    # Save to JSON
    output_json = args.output_dir / "variant_selection.json"
    summary_payload = {
        "model": "nomic-embed-text",
        "digest": embedder.digest,
        "ollama_version": embedder.version,
        "dataset_split": "train.jsonl (N=480)",
        "cv_folds": 5,
        "seed": 42,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "results": [
            {k: v for k, v in r.items() if k != "predictions"}
            for r in results
        ],
    }
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(summary_payload, f, indent=2)
    print(f"\nSaved variant selection JSON to {output_json}")

    # Print markdown table
    print("\n" + "=" * 80)
    print("5-FOLD CROSS-VALIDATION VARIANT SELECTION (TRAIN SPLIT N=480, k=5)")
    print("=" * 80)
    print("| Variant | Stored (Doc) Prefix | Query Prefix | Category Acc [95% CI] | Cat Macro-F1 | Priority Acc [95% CI] | Priority Within-One | Combined Acc |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    for r in results:
        print(
            f"| **`{r['variant']}`** | `{r['doc_prefix'].strip() or '(none)'}` | `{r['query_prefix'].strip() or '(none)'}` | "
            f"{r['category_accuracy']*100:.1f}% [{r['category_ci'][0]*100:.1f}%, {r['category_ci'][1]*100:.1f}%] | "
            f"{r['macro_f1']:.4f} | "
            f"{r['priority_accuracy']*100:.1f}% [{r['priority_ci'][0]*100:.1f}%, {r['priority_ci'][1]*100:.1f}%] | "
            f"{r['priority_within_one']*100:.1f}% | "
            f"{r['combined_accuracy']*100:.1f}% |"
        )

    best = results[0]
    print(f"\nWINNING VARIANT: '{best['variant']}' (Cat Acc: {best['category_accuracy']*100:.1f}%, Prio Acc: {best['priority_accuracy']*100:.1f}%)")


if __name__ == "__main__":
    main()

