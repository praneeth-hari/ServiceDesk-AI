"""
Pre-registered benchmark for keyword-stuffing mitigations on hashing-v2 kNN triage.

Evaluates term frequency capping on HashingEmbedder:
- baseline: hashing-v2 (no cap)
- A1, A2, A3: query-side cap at 1, 2, 3 (stored vectors unchanged)
- B1, B2, B3: cap at 1, 2, 3 on both stored and query vectors

Follows benchmarks/STUFFING_PREREG.md protocol:
Step 1: 5-fold CV on train split (n=480). Eligible if cat and prio within 1.0 pp of baseline.
Step 2: Selection on stuffing_dev (n=20). Fewest successes, tie break: A over B, larger cap.
        Stop if baseline < 8 or best reduction < 40%.
Step 3: If not stopped, single evaluation of winner vs baseline on test split (n=120),
        dev injection (n=40), held-out lexical stuffing (n=8), and held-out pooled (n=60).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from sklearn.model_selection import StratifiedKFold

from app.ai.dataset import TicketExample, load_split
from app.ai.embedder import HashingEmbedder
from app.models.enums import TicketCategory, TicketPriority
from app.scripts.benchmark_triage import compute_mcnemar_exact_test
from app.services.triage import predict_knn

DEFAULT_OUTPUT_DIR = Path("benchmarks") / "results_stuffing"
DEFAULT_STUFFING_DEV_PATH = Path("data") / "injection" / "stuffing_dev.jsonl"
DEFAULT_DEV_INJECTION_PATH = Path("data") / "injection" / "injection_set.jsonl"
DEFAULT_HELDOUT_V1_PATH = Path("data") / "injection" / "heldout_set.jsonl"
DEFAULT_HELDOUT_V2_PATH = Path("data") / "injection" / "heldout_v2.jsonl"

CANDIDATES: dict[str, tuple[int | None, int | None]] = {
    "baseline": (None, None),
    "A1": (None, 1),
    "A2": (None, 2),
    "A3": (None, 3),
    "B1": (1, 1),
    "B2": (2, 2),
    "B3": (3, 3),
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    tickets = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                tickets.append(json.loads(line))
    return tickets


def get_stuffing_style(ticket_id: str) -> str:
    parts = ticket_id.split("-")
    try:
        num = int(parts[-1])
    except ValueError:
        return "unknown"
    if 1 <= num <= 12:
        return "keyword_list"
    elif 13 <= num <= 16:
        return "repeated_words"
    else:
        return "interleaved"


def evaluate_knn_batch(
    train_tickets: Sequence[TicketExample],
    train_vecs: np.ndarray,
    query_texts: Sequence[str],
    query_vecs: np.ndarray,
    k: int = 5,
    min_similarity: float = 0.12,
) -> list[tuple[TicketCategory | None, TicketPriority | None, float]]:
    results = []
    n_train = len(train_tickets)
    for i in range(len(query_texts)):
        sims = np.dot(train_vecs, query_vecs[i])
        candidates = [
            {
                "category": TicketCategory(train_tickets[j].category),
                "priority": TicketPriority(train_tickets[j].priority),
                "similarity": float(sims[j]),
            }
            for j in range(n_train)
        ]
        pred_cat, pred_prio, conf = predict_knn(candidates, k=k, min_similarity=min_similarity)
        results.append((pred_cat, pred_prio, conf))
    return results


def run_step1_cv(
    train_tickets: list[TicketExample],
    output_dir: Path,
    n_splits: int = 5,
    random_state: int = 42,
) -> dict[str, Any]:
    print("\n" + "=" * 70)
    print("STEP 1: 5-Fold Cross-Validation on Train Split (n=480)")
    print("=" * 70)

    train_texts = [t.text for t in train_tickets]
    train_cats = [t.category for t in train_tickets]

    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    folds = list(skf.split(train_texts, train_cats))

    cv_results: dict[str, Any] = {}
    total = len(train_tickets)

    # Run baseline first to establish reference accuracies
    for name, (cap_tr, cap_q) in CANDIDATES.items():
        emb_tr = HashingEmbedder(cap=cap_tr)
        emb_q = HashingEmbedder(cap=cap_q) if cap_q != cap_tr else emb_tr

        train_vecs_all = np.vstack(emb_tr.embed(train_texts)).astype(np.float32)
        val_vecs_all = (
            np.vstack(emb_q.embed(train_texts)).astype(np.float32)
            if cap_q != cap_tr
            else train_vecs_all
        )

        n_cat_correct = 0
        n_prio_correct = 0

        for tr_idx, val_idx in folds:
            f_tr_vecs = train_vecs_all[tr_idx]
            f_val_vecs = val_vecs_all[val_idx]

            for i, vi in enumerate(val_idx):
                sims = np.dot(f_tr_vecs, f_val_vecs[i])
                cands = [
                    {
                        "category": TicketCategory(train_tickets[tr_idx[j]].category),
                        "priority": TicketPriority(train_tickets[tr_idx[j]].priority),
                        "similarity": float(sims[j]),
                    }
                    for j in range(len(tr_idx))
                ]
                pred_cat, pred_prio, _ = predict_knn(cands, k=5, min_similarity=0.12)
                if pred_cat and pred_cat.value == train_tickets[vi].category:
                    n_cat_correct += 1
                if pred_prio and pred_prio.value == train_tickets[vi].priority:
                    n_prio_correct += 1

        cat_acc = n_cat_correct / total
        prio_acc = n_prio_correct / total

        cv_results[name] = {
            "name": name,
            "cap_train": cap_tr,
            "cap_query": cap_q,
            "category_correct": n_cat_correct,
            "category_accuracy": round(cat_acc, 4),
            "priority_correct": n_prio_correct,
            "priority_accuracy": round(prio_acc, 4),
            "total": total,
        }

    base_cat = cv_results["baseline"]["category_accuracy"]
    base_prio = cv_results["baseline"]["priority_accuracy"]

    for name, d in cv_results.items():
        cat_delta_pp = round((d["category_accuracy"] - base_cat) * 100.0, 2)
        prio_delta_pp = round((d["priority_accuracy"] - base_prio) * 100.0, 2)
        eligible = (abs(cat_delta_pp) <= 1.0) and (abs(prio_delta_pp) <= 1.0)
        d["cat_delta_pp"] = cat_delta_pp
        d["prio_delta_pp"] = prio_delta_pp
        d["eligible"] = eligible

        status = "ELIGIBLE" if eligible else "INELIGIBLE"
        print(
            f"  {name:<10}: Cat {d['category_accuracy']:.1%} ({cat_delta_pp:+.2f} pp), "
            f"Prio {d['priority_accuracy']:.1%} ({prio_delta_pp:+.2f} pp) -> {status}"
        )

    out_file = output_dir / "step1_cv.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(cv_results, f, indent=2)

    return cv_results


def evaluate_injection_tickets(
    train_tickets: list[TicketExample],
    test_tickets: list[dict[str, Any]],
    cap_train: int | None,
    cap_query: int | None,
) -> tuple[int, dict[str, int], list[dict[str, Any]]]:
    emb_tr = HashingEmbedder(cap=cap_train)
    emb_q = HashingEmbedder(cap=cap_query) if cap_query != cap_train else emb_tr

    train_texts = [t.text for t in train_tickets]
    train_vecs = np.vstack(emb_tr.embed(train_texts)).astype(np.float32)

    query_texts = [f"{t['title']}\n{t['description']}" for t in test_tickets]
    query_vecs = np.vstack(emb_q.embed(query_texts)).astype(np.float32)

    preds = evaluate_knn_batch(train_tickets, train_vecs, query_texts, query_vecs)

    successes = 0
    by_style = {"keyword_list": 0, "repeated_words": 0, "interleaved": 0}
    per_ticket = []

    for i, t in enumerate(test_tickets):
        pred_cat, pred_prio, conf = preds[i]
        target = t["injected_target"]
        field = t["injected_field"]

        is_succ = False
        if field == "category":
            if pred_cat and pred_cat.value == target:
                is_succ = True
        else:
            if pred_prio and pred_prio.value == target:
                is_succ = True

        style = get_stuffing_style(t["id"])
        if is_succ:
            successes += 1
            if style in by_style:
                by_style[style] += 1

        per_ticket.append(
            {
                "id": t["id"],
                "style": style,
                "injected_field": field,
                "injected_target": target,
                "predicted_category": pred_cat.value if pred_cat else None,
                "predicted_priority": pred_prio.value if pred_prio else None,
                "confidence": conf,
                "attack_success": is_succ,
            }
        )

    return successes, by_style, per_ticket


def run_step2_selection(
    train_tickets: list[TicketExample],
    stuffing_tickets: list[dict[str, Any]],
    cv_results: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    print("\n" + "=" * 70)
    print("STEP 2: Selection on stuffing_dev (n=20)")
    print("=" * 70)

    n_stuffing = len(stuffing_tickets)

    # Evaluate baseline
    base_succ, base_by_style, base_per_ticket = evaluate_injection_tickets(
        train_tickets, stuffing_tickets, cap_train=None, cap_query=None
    )

    step2_results: dict[str, Any] = {
        "n": n_stuffing,
        "baseline": {
            "name": "baseline",
            "attack_successes": base_succ,
            "attack_success_rate": round(base_succ / n_stuffing, 4),
            "by_style": base_by_style,
            "per_ticket": base_per_ticket,
        },
        "candidates": {},
    }

    print(
        f"  Baseline: {base_succ}/{n_stuffing} successes ({base_succ / n_stuffing:.1%}) "
        f"[keyword_list: {base_by_style['keyword_list']}/12, "
        f"repeated: {base_by_style['repeated_words']}/4, "
        f"interleaved: {base_by_style['interleaved']}/4]"
    )

    # Stop rule 1: baseline < 8
    stop_uninformative = base_succ < 8

    # Evaluate all eligible candidates
    eligible_names = [k for k, v in cv_results.items() if k != "baseline" and v.get("eligible")]

    best_candidate: str | None = None
    min_successes = 999

    for name in eligible_names:
        cap_tr, cap_q = CANDIDATES[name]
        succ, by_style, per_ticket = evaluate_injection_tickets(
            train_tickets, stuffing_tickets, cap_train=cap_tr, cap_query=cap_q
        )
        reduction_pct = round(((base_succ - succ) / base_succ) * 100.0, 2) if base_succ > 0 else 0.0

        step2_results["candidates"][name] = {
            "name": name,
            "attack_successes": succ,
            "attack_success_rate": round(succ / n_stuffing, 4),
            "reduction_pct": reduction_pct,
            "by_style": by_style,
            "per_ticket": per_ticket,
        }

        print(
            f"  Candidate {name:<4}: {succ}/{n_stuffing} successes ({reduction_pct:+.1f}% vs baseline) "
            f"[kw: {by_style['keyword_list']}/12, rep: {by_style['repeated_words']}/4, "
            f"int: {by_style['interleaved']}/4]"
        )

    # Pick winner among eligible candidates: fewest successes.
    # Ties: prefer A over B, then larger cap.
    def candidate_sort_key(c_name: str) -> tuple[int, int, int]:
        d = step2_results["candidates"][c_name]
        succ = d["attack_successes"]
        # Prefer A over B: 0 for A, 1 for B
        family_rank = 0 if c_name.startswith("A") else 1
        # Prefer larger cap: -cap
        cap_val = CANDIDATES[c_name][1] or 0
        return (succ, family_rank, -cap_val)

    if eligible_names:
        sorted_candidates = sorted(eligible_names, key=candidate_sort_key)
        best_candidate = sorted_candidates[0]
        best_succ = step2_results["candidates"][best_candidate]["attack_successes"]
        best_reduction = (base_succ - best_succ) / base_succ if base_succ > 0 else 0.0
    else:
        best_candidate = None
        best_reduction = 0.0

    stop_no_effective_cap = best_reduction < 0.40 if not stop_uninformative else False

    stopped = stop_uninformative or stop_no_effective_cap
    stop_reason = None
    if stop_uninformative:
        stop_reason = f"Uninformative set: baseline had {base_succ} < 8 successes."
    elif stop_no_effective_cap:
        stop_reason = (
            f"No effective cap: best candidate ({best_candidate}) achieved "
            f"{best_reduction:.1%} reduction (< 40% required)."
        )

    step2_results["stop_rule_uninformative"] = stop_uninformative
    step2_results["stop_rule_no_effective_cap"] = stop_no_effective_cap
    step2_results["stopped"] = stopped
    step2_results["stop_reason"] = stop_reason
    step2_results["winner"] = best_candidate if not stopped else None

    if stopped:
        print(f"  STOP TRIGGERED: {stop_reason}")
    else:
        print(f"  WINNER: {best_candidate} (proceeding to Step 3)")

    out_file = output_dir / "step2_selection.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(step2_results, f, indent=2)

    return step2_results


def run_step3_eval(
    train_tickets: list[TicketExample],
    winner_name: str,
    output_dir: Path,
) -> dict[str, Any]:
    print("\n" + "=" * 70)
    print(f"STEP 3: Single Evaluation of Winner ({winner_name}) vs Baseline")
    print("=" * 70)

    cap_tr_w, cap_q_w = CANDIDATES[winner_name]

    # (a) Test split (n=120)
    test_tickets = load_split("test")
    test_texts = [t.text for t in test_tickets]

    emb_tr_b = HashingEmbedder(cap=None)
    tr_vecs_b = np.vstack(emb_tr_b.embed([t.text for t in train_tickets])).astype(np.float32)
    q_vecs_b = np.vstack(emb_tr_b.embed(test_texts)).astype(np.float32)
    preds_b = evaluate_knn_batch(train_tickets, tr_vecs_b, test_texts, q_vecs_b)

    emb_tr_w = HashingEmbedder(cap=cap_tr_w)
    emb_q_w = HashingEmbedder(cap=cap_q_w) if cap_q_w != cap_tr_w else emb_tr_w
    tr_vecs_w = np.vstack(emb_tr_w.embed([t.text for t in train_tickets])).astype(np.float32)
    q_vecs_w = np.vstack(emb_q_w.embed(test_texts)).astype(np.float32)
    preds_w = evaluate_knn_batch(train_tickets, tr_vecs_w, test_texts, q_vecs_w)

    n_test = len(test_tickets)
    b_cat_corr = [preds_b[i][0] is not None and preds_b[i][0].value == test_tickets[i].category for i in range(n_test)]
    w_cat_corr = [preds_w[i][0] is not None and preds_w[i][0].value == test_tickets[i].category for i in range(n_test)]
    b_prio_corr = [preds_b[i][1] is not None and preds_b[i][1].value == test_tickets[i].priority for i in range(n_test)]
    w_prio_corr = [preds_w[i][1] is not None and preds_w[i][1].value == test_tickets[i].priority for i in range(n_test)]

    cat_acc_b = sum(b_cat_corr) / n_test
    cat_acc_w = sum(w_cat_corr) / n_test
    prio_acc_b = sum(b_prio_corr) / n_test
    prio_acc_w = sum(w_prio_corr) / n_test

    mcn_b_cat, mcn_c_cat, mcn_p_cat = compute_mcnemar_exact_test(w_cat_corr, b_cat_corr)
    mcn_b_prio, mcn_c_prio, mcn_p_prio = compute_mcnemar_exact_test(w_prio_corr, b_prio_corr)

    cat_delta_pp = round((cat_acc_w - cat_acc_b) * 100.0, 2)
    prio_delta_pp = round((prio_acc_w - prio_acc_b) * 100.0, 2)

    # Condition (a): not worse by > 2.0 pp
    cond_a = (cat_delta_pp >= -2.0) and (prio_delta_pp >= -2.0)

    # (b) Held-out v1+v2 lexical_stuffing (n=8)
    heldout_v1 = load_jsonl(DEFAULT_HELDOUT_V1_PATH)
    heldout_v2 = load_jsonl(DEFAULT_HELDOUT_V2_PATH)
    stuffing_v1 = [t for t in heldout_v1 if t.get("attack_type") == "lexical_stuffing"]
    stuffing_v2 = [t for t in heldout_v2 if t.get("attack_type") == "lexical_stuffing"]
    heldout_stuffing_8 = stuffing_v1 + stuffing_v2
    assert len(heldout_stuffing_8) == 8, f"Expected 8 heldout stuffing tickets, found {len(heldout_stuffing_8)}"

    succ_b_stuff8, _, _ = evaluate_injection_tickets(train_tickets, heldout_stuffing_8, None, None)
    succ_w_stuff8, _, _ = evaluate_injection_tickets(train_tickets, heldout_stuffing_8, cap_tr_w, cap_q_w)
    cond_b = succ_w_stuff8 <= 4

    # (c) Held-out v1+v2 pooled (n=60)
    heldout_pooled_60 = heldout_v1 + heldout_v2
    assert len(heldout_pooled_60) == 60, f"Expected 60 heldout tickets, found {len(heldout_pooled_60)}"

    succ_b_pool60, _, _ = evaluate_injection_tickets(train_tickets, heldout_pooled_60, None, None)
    succ_w_pool60, _, _ = evaluate_injection_tickets(train_tickets, heldout_pooled_60, cap_tr_w, cap_q_w)
    cond_c = succ_w_pool60 <= succ_b_pool60

    # (d) Dev injection set (n=40)
    dev_tickets_40 = load_jsonl(DEFAULT_DEV_INJECTION_PATH)
    assert len(dev_tickets_40) == 40, f"Expected 40 dev injection tickets, found {len(dev_tickets_40)}"

    succ_b_dev40, _, _ = evaluate_injection_tickets(train_tickets, dev_tickets_40, None, None)
    succ_w_dev40, _, _ = evaluate_injection_tickets(train_tickets, dev_tickets_40, cap_tr_w, cap_q_w)
    cond_d = succ_w_dev40 <= (succ_b_dev40 + 1)

    all_passed = cond_a and cond_b and cond_c and cond_d
    decision = "ADOPT" if all_passed else "DO NOT ADOPT"

    step3_results: dict[str, Any] = {
        "winner": winner_name,
        "test_split": {
            "n": n_test,
            "baseline_cat_acc": round(cat_acc_b, 4),
            "winner_cat_acc": round(cat_acc_w, 4),
            "cat_delta_pp": cat_delta_pp,
            "mcnemar_cat": {"b": mcn_b_cat, "c": mcn_c_cat, "p_value": round(mcn_p_cat, 4)},
            "baseline_prio_acc": round(prio_acc_b, 4),
            "winner_prio_acc": round(prio_acc_w, 4),
            "prio_delta_pp": prio_delta_pp,
            "mcnemar_prio": {"b": mcn_b_prio, "c": mcn_c_prio, "p_value": round(mcn_p_prio, 4)},
        },
        "heldout_lexical_stuffing": {
            "n": 8,
            "baseline_successes": succ_b_stuff8,
            "winner_successes": succ_w_stuff8,
        },
        "heldout_pooled": {
            "n": 60,
            "baseline_successes": succ_b_pool60,
            "winner_successes": succ_w_pool60,
        },
        "dev_injection": {
            "n": 40,
            "baseline_successes": succ_b_dev40,
            "winner_successes": succ_w_dev40,
        },
        "conditions": {
            "condition_a": {
                "desc": "test split cat & prio not worse by > 2.0 pp",
                "passed": bool(cond_a),
                "details": f"Cat {cat_delta_pp:+.2f} pp, Prio {prio_delta_pp:+.2f} pp",
            },
            "condition_b": {
                "desc": "held-out v1+v2 lexical_stuffing successes <= 4 of 8",
                "passed": bool(cond_b),
                "details": f"{succ_w_stuff8}/8 (baseline {succ_b_stuff8}/8)",
            },
            "condition_c": {
                "desc": "held-out v1+v2 pooled successes (n=60) not higher than hashing-v2",
                "passed": bool(cond_c),
                "details": f"{succ_w_pool60}/60 (baseline {succ_b_pool60}/60)",
            },
            "condition_d": {
                "desc": "dev injection set successes (n=40) not more than hashing-v2 plus 1",
                "passed": bool(cond_d),
                "details": f"{succ_w_dev40}/40 (baseline {succ_b_dev40}/40)",
            },
        },
        "all_passed": bool(all_passed),
        "decision": decision,
    }

    print(f"  Test split Cat Acc : baseline {cat_acc_b:.1%} vs winner {cat_acc_w:.1%} ({cat_delta_pp:+.2f} pp, p={mcn_p_cat:.4f})")
    print(f"  Test split Prio Acc: baseline {prio_acc_b:.1%} vs winner {prio_acc_w:.1%} ({prio_delta_pp:+.2f} pp, p={mcn_p_prio:.4f})")
    print(f"  Held-out Stuffing  : baseline {succ_b_stuff8}/8 vs winner {succ_w_stuff8}/8 (cond_b: {cond_b})")
    print(f"  Held-out Pooled    : baseline {succ_b_pool60}/60 vs winner {succ_w_pool60}/60 (cond_c: {cond_c})")
    print(f"  Dev Injection      : baseline {succ_b_dev40}/40 vs winner {succ_w_dev40}/40 (cond_d: {cond_d})")
    print(f"  DECISION: {decision}")

    out_file = output_dir / "step3_eval.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(step3_results, f, indent=2)

    return step3_results


def run_benchmark(output_dir: Path = DEFAULT_OUTPUT_DIR) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    train_tickets = load_split("train")
    stuffing_tickets = load_jsonl(DEFAULT_STUFFING_DEV_PATH)

    cv_results = run_step1_cv(train_tickets, output_dir)
    step2_results = run_step2_selection(train_tickets, stuffing_tickets, cv_results, output_dir)

    if not step2_results["stopped"]:
        winner = step2_results["winner"]
        run_step3_eval(train_tickets, winner, output_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    run_benchmark(args.output_dir)

