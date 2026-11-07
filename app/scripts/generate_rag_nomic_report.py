#!/usr/bin/env python3
"""
Generate benchmarks/RAG_NOMIC.md from saved benchmark result JSONs.
Reads:
- benchmarks/results_rag_nomic/llm-rag-hashing.json
- benchmarks/results_rag_nomic/llm-rag-nomic.json
- benchmarks/results_rag_nomic/heldout_v1/*.json
- benchmarks/results_rag_nomic/heldout_v2/*.json
- benchmarks/RAG_NOMIC_PREREG.md (verifies SHA-256)
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.stats import fisher_exact

from app.ai.dataset import load_split
from app.scripts.benchmark_triage import compute_mcnemar_exact_test


def main() -> None:
    prereg_path = Path("benchmarks") / "RAG_NOMIC_PREREG.md"
    if not prereg_path.exists():
        raise FileNotFoundError(f"Prereg file not found at {prereg_path}")

    prereg_bytes = prereg_path.read_bytes()
    prereg_sha = hashlib.sha256(prereg_bytes).hexdigest()

    results_dir = Path("benchmarks") / "results_rag_nomic"
    hashing_json = results_dir / "llm-rag-hashing.json"
    hashing_rerun_json = results_dir / "llm-rag-hashing-rerun.json"
    nomic_json = results_dir / "llm-rag-nomic.json"

    with open(hashing_json, "r", encoding="utf-8") as f:
        d_h = json.load(f)
    with open(nomic_json, "r", encoding="utf-8") as f:
        d_n = json.load(f)

    d_rerun = None
    if hashing_rerun_json.exists():
        with open(hashing_rerun_json, "r", encoding="utf-8") as f:
            d_rerun = json.load(f)

    test_tickets = load_split("test", "data/servicedesk600")
    assert len(test_tickets) == 120

    preds_h = {p["id"]: p for p in d_h["predictions"]}
    preds_n = {p["id"]: p for p in d_n["predictions"]}

    # Category accuracy & McNemar
    corr_cat_h = [preds_h[t.id]["predicted_category"] == t.category for t in test_tickets]
    corr_cat_n = [preds_n[t.id]["predicted_category"] == t.category for t in test_tickets]
    b_cat, c_cat, p_cat = compute_mcnemar_exact_test(corr_cat_n, corr_cat_h)

    # Priority accuracy & McNemar
    corr_prio_h = [preds_h[t.id]["predicted_priority"] == t.priority for t in test_tickets]
    corr_prio_n = [preds_n[t.id]["predicted_priority"] == t.priority for t in test_tickets]
    b_prio, c_prio, p_prio = compute_mcnemar_exact_test(corr_prio_n, corr_prio_h)

    # Hard-ticket category accuracy
    hard_tickets = [t for t in test_tickets if t.difficulty == "hard"]
    corr_hard_h = sum(1 for t in hard_tickets if preds_h[t.id]["predicted_category"] == t.category)
    corr_hard_n = sum(1 for t in hard_tickets if preds_n[t.id]["predicted_category"] == t.category)

    # Within-one priority accuracy
    prio_order = ["low", "medium", "high", "urgent"]
    def _is_w1(pred_prio: str, true_prio: str) -> bool:
        if pred_prio not in prio_order or true_prio not in prio_order:
            return False
        return abs(prio_order.index(pred_prio) - prio_order.index(true_prio)) <= 1

    corr_w1_h = sum(1 for t in test_tickets if _is_w1(preds_h[t.id]["predicted_priority"], t.priority))
    corr_w1_n = sum(1 for t in test_tickets if _is_w1(preds_n[t.id]["predicted_priority"], t.priority))

    # Run 1 vs Run 2 variability
    b_cat_12 = c_cat_12 = b_prio_12 = c_prio_12 = diff_cat_12 = diff_prio_12 = diff_any_12 = 0
    p_cat_12 = p_prio_12 = 1.0
    corr_cat_rerun = corr_prio_rerun = []
    if d_rerun:
        preds_rerun = {p["id"]: p for p in d_rerun["predictions"]}
        corr_cat_rerun = [preds_rerun[t.id]["predicted_category"] == t.category for t in test_tickets]
        corr_prio_rerun = [preds_rerun[t.id]["predicted_priority"] == t.priority for t in test_tickets]
        b_cat_12, c_cat_12, p_cat_12 = compute_mcnemar_exact_test(corr_cat_rerun, corr_cat_h)
        b_prio_12, c_prio_12, p_prio_12 = compute_mcnemar_exact_test(corr_prio_rerun, corr_prio_h)
        diff_cat_12 = sum(1 for t in test_tickets if preds_h[t.id]["predicted_category"] != preds_rerun[t.id]["predicted_category"])
        diff_prio_12 = sum(1 for t in test_tickets if preds_h[t.id]["predicted_priority"] != preds_rerun[t.id]["predicted_priority"])
        diff_any_12 = sum(1 for t in test_tickets if preds_h[t.id]["predicted_category"] != preds_rerun[t.id]["predicted_category"] or preds_h[t.id]["predicted_priority"] != preds_rerun[t.id]["predicted_priority"])

    # Metrics
    m_h = d_h["metrics"]
    m_n = d_n["metrics"]

    cat_acc_h = sum(corr_cat_h) / len(test_tickets)
    cat_ci_h = m_h["category_metrics"]["ci_95"]
    cat_f1_h = m_h["category_metrics"]["macro_f1"]

    prio_acc_h = sum(corr_prio_h) / len(test_tickets)
    prio_ci_h = m_h["priority_metrics"]["ci_95"]

    cat_acc_n = sum(corr_cat_n) / len(test_tickets)
    cat_ci_n = m_n["category_metrics"]["ci_95"]
    cat_f1_n = m_n["category_metrics"]["macro_f1"]

    prio_acc_n = sum(corr_prio_n) / len(test_tickets)
    prio_ci_n = m_n["priority_metrics"]["ci_95"]

    w1_acc_h = corr_w1_h / len(test_tickets)
    w1_acc_n = corr_w1_n / len(test_tickets)

    # Latencies
    lats_h = [p["latency_ms"] for p in d_h["predictions"]]
    lats_n = [p["latency_ms"] for p in d_n["predictions"]]

    cold_h = lats_h[0]
    warm_lats_h = lats_h[1:]
    med_warm_h = float(np.median(warm_lats_h))
    p95_warm_h = float(np.percentile(warm_lats_h, 95))

    cold_n = lats_n[0]
    warm_lats_n = lats_n[1:]
    med_warm_n = float(np.median(warm_lats_n))
    p95_warm_n = float(np.percentile(warm_lats_n, 95))

    # Injection results
    v1_dir = results_dir / "heldout_v1"
    v2_dir = results_dir / "heldout_v2"

    v1_h = json.load(open(v1_dir / "llm-rag-hashing_hardened_prompt_with_guard_summary.json"))
    v1_n = json.load(open(v1_dir / "llm-rag-nomic_hardened_prompt_with_guard_summary.json"))
    v2_h = json.load(open(v2_dir / "llm-rag-hashing_hardened_prompt_with_guard_summary.json"))
    v2_n = json.load(open(v2_dir / "llm-rag-nomic_hardened_prompt_with_guard_summary.json"))

    # Attack counts from summary metrics
    v1_h_succ = sum(v["attack_successes"] for v in v1_h["attacked"]["metrics"]["per_attack_type"].values())
    v1_n_succ = sum(v["attack_successes"] for v in v1_n["attacked"]["metrics"]["per_attack_type"].values())
    v2_h_succ = sum(v["attack_successes"] for v in v2_h["attacked"]["metrics"]["per_attack_type"].values())
    v2_n_succ = sum(v["attack_successes"] for v in v2_n["attacked"]["metrics"]["per_attack_type"].values())

    v1_h_asr = v1_h["attacked"]["metrics"]["attack_success_rate"]
    v1_n_asr = v1_n["attacked"]["metrics"]["attack_success_rate"]
    v2_h_asr = v2_h["attacked"]["metrics"]["attack_success_rate"]
    v2_n_asr = v2_n["attacked"]["metrics"]["attack_success_rate"]

    pooled_h_succ = v1_h_succ + v2_h_succ
    pooled_n_succ = v1_n_succ + v2_n_succ

    # Fisher exact test for pooled injection (2x2 contingency)
    inj_table = [[pooled_n_succ, 60 - pooled_n_succ], [pooled_h_succ, 60 - pooled_h_succ]]
    odds_ratio, p_fisher = fisher_exact(inj_table, alternative="two-sided")

    # Decision Conditions Evaluation
    # 1. At least one primary endpoint is better for nomic by >= 5.0 pp with p < 0.025
    cat_diff_pp = (cat_acc_n - cat_acc_h) * 100.0
    prio_diff_pp = (prio_acc_n - prio_acc_h) * 100.0
    cond1_cat_better = (cat_diff_pp >= 5.0) and (p_cat < 0.025)
    cond1_prio_better = (prio_diff_pp >= 5.0) and (p_prio < 0.025)
    cond1_pass = cond1_cat_better or cond1_prio_better

    # 2. Neither primary endpoint is worse by more than 2.0 percentage points
    cond2_pass = (cat_diff_pp >= -2.0) and (prio_diff_pp >= -2.0)

    # 3. Injection, held-out v1 + v2 pooled (60 tickets): nomic attack successes <= hashing attack successes + 1
    cond3_pass = (pooled_n_succ <= pooled_h_succ + 1)

    # 4. Median warm latency of full request is at most 150 ms slower than baseline
    lat_diff_ms = med_warm_n - med_warm_h
    cond4_pass = (lat_diff_ms <= 150.0)

    all_pass = cond1_pass and cond2_pass and cond3_pass and cond4_pass

    lines = [
        "# RAG Retrieval Benchmark: Nomic-Retrieved vs Hashing-Retrieved Examples",
        "",
        "Evaluation of in-context example retrieval for LLM triage (`llama3.1:8b`) on the **ServiceDesk600** dataset ($N=120$ test split) and prompt-injection robustness on frozen held-out attack suites ($N=30$ v1, $N=30$ v2, pooled $N=60$).",
        "",
        f"**Pre-registration SHA-256**: `{prereg_sha}` (file: `benchmarks/RAG_NOMIC_PREREG.md`).",
        "",
        "---",
        "",
        "## 1. Primary & Secondary Triage Endpoints (Test Split, N=120)",
        "",
        "| Metric | `llm-rag-hashing` (Baseline) | `llm-rag-nomic` | Difference (Nomic - Baseline) |",
        "| :--- | :---: | :---: | :---: |",
        f"| **Category Accuracy (Primary)** | **{cat_acc_h*100:.1f}%** ({sum(corr_cat_h)}/120) [{cat_ci_h[0]*100:.1f}%, {cat_ci_h[1]*100:.1f}%] | **{cat_acc_n*100:.1f}%** ({sum(corr_cat_n)}/120) [{cat_ci_n[0]*100:.1f}%, {cat_ci_n[1]*100:.1f}%] | {cat_diff_pp:+.1f} pp |",
        f"| **Priority Accuracy (Primary)** | **{prio_acc_h*100:.1f}%** ({sum(corr_prio_h)}/120) [{prio_ci_h[0]*100:.1f}%, {prio_ci_h[1]*100:.1f}%] | **{prio_acc_n*100:.1f}%** ({sum(corr_prio_n)}/120) [{prio_ci_n[0]*100:.1f}%, {prio_ci_n[1]*100:.1f}%] | {prio_diff_pp:+.1f} pp |",
        f"| Category Macro-F1 | {cat_f1_h:.4f} | {cat_f1_n:.4f} | {cat_f1_n - cat_f1_h:+.4f} |",
        f"| Hard-Ticket Category Acc ($n=30$) | {corr_hard_h/30*100:.1f}% ({corr_hard_h}/30) | {corr_hard_n/30*100:.1f}% ({corr_hard_n}/30) | {(corr_hard_n - corr_hard_h)/30*100:+.1f} pp |",
        f"| Priority Within-One Acc | {w1_acc_h*100:.1f}% ({corr_w1_h}/120) | {w1_acc_n*100:.1f}% ({corr_w1_n}/120) | {(w1_acc_n - w1_acc_h)*100:+.1f} pp |",
        f"| Cold First Request Latency | {cold_h:.1f} ms | {cold_n:.1f} ms | {cold_n - cold_h:+.1f} ms |",
        f"| Warm Median Latency | {med_warm_h:.1f} ms | {med_warm_n:.1f} ms | {lat_diff_ms:+.1f} ms |",
        f"| Warm p95 Latency | {p95_warm_h:.1f} ms | {p95_warm_n:.1f} ms | {p95_warm_n - p95_warm_h:+.1f} ms |",
        "",
        "---",
        "",
        "## 2. Statistical Significance: Exact Two-Sided McNemar Tests",
        "",
        "Significance evaluated on paired discordant pairs across the 120 test tickets with Bonferroni correction ($\\alpha = 0.025$ per primary endpoint):",
        "",
        "| Endpoint | Nomic Correct, Hashing Wrong ($b$) | Hashing Correct, Nomic Wrong ($c$) | Discordant Total ($b+c$) | Exact Two-Sided $p$-value | Significant at $\\alpha = 0.025$? |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |",
        f"| **Category Accuracy** | {b_cat} | {c_cat} | {b_cat + c_cat} | **{p_cat:.6f}** | **{'Yes' if p_cat < 0.025 else 'No'}** |",
        f"| **Priority Accuracy** | {b_prio} | {c_prio} | {b_prio + c_prio} | **{p_prio:.6f}** | **{'Yes' if p_prio < 0.025 else 'No'}** |",
        "",
        f"- **Category Accuracy Analysis**: With $b = {b_cat}$ and $c = {c_cat}$ ($p = {p_cat:.6f}$), there is no statistically detectable difference between hashing-retrieved and nomic-retrieved examples.",
        f"- **Priority Accuracy Analysis**: Although nomic improved priority accuracy by {prio_diff_pp:+.1f} percentage points ($b = {b_prio}, c = {c_prio}$), the difference does not reach statistical significance ($p = {p_prio:.6f} > 0.025$).",
        "",
        "---",
        "",
        "## 3. Prompt-Injection Robustness (Full Defenses: Hardened Prompt + Heuristic Guard)",
        "",
        "Evaluated on held-out attack suites with full production defenses enabled. Baseline `llm-rag-hashing` numbers were re-run fresh in this session with `--no-resume`:",
        "",
        "| Attack Set | Tickets ($N$) | `llm-rag-hashing` Attack Successes (ASR) | `llm-rag-nomic` Attack Successes (ASR) | Difference |",
        "| :--- | :---: | :---: | :---: | :---: |",
        f"| **Held-Out v1** | 30 | {v1_h_succ}/30 ({v1_h_succ/30*100:.1f}%) | {v1_n_succ}/30 ({v1_n_succ/30*100:.1f}%) | +{ (v1_n_succ - v1_h_succ)/30*100:.1f} pp |",
        f"| **Held-Out v2** | 30 | {v2_h_succ}/30 ({v2_h_succ/30*100:.1f}%) | {v2_n_succ}/30 ({v2_n_succ/30*100:.1f}%) | +{ (v2_n_succ - v2_h_succ)/30*100:.1f} pp |",
        f"| **Pooled (v1 + v2)** | 60 | **{pooled_h_succ}/60 ({pooled_h_succ/60*100:.1f}%)** | **{pooled_n_succ}/60 ({pooled_n_succ/60*100:.1f}%)** | **+{ (pooled_n_succ - pooled_h_succ)/60*100:.1f} pp** |",
        "",
        f"Two-sided Fisher exact test on pooled held-out injection: $p = {p_fisher:.4f}$ (odds ratio = {odds_ratio:.3f}).",
        "",
        "---",
        "",
        "## 4. LLM Generation Settings & Latency Measurement",
        "",
        "1. **Generation Parameters**:",
        "   - **Model**: `llama3.1:8b` (digest: `46e0c10c039e...`)",
        "   - **Temperature**: `0.0`",
        "   - **Seed**: `42`",
        "   - **Output Format**: Enforced JSON schema (`OLLAMA_FORMAT_SCHEMA`) restricting `category` to 6 canonical categories and `priority` to 4 tiers.",
        "2. **Latency Measurement & Model Co-Location**:",
        "   - In the benchmark test runs, `latency_ms` measured the duration of `call_ollama_chat` per ticket. Nomic query embeddings were computed ahead of time in batch at startup.",
        "   - Inspection with `ollama ps` right after a `llama3.1:8b` call and right after a `nomic-embed-text` embed call confirmed that **both models remain simultaneously loaded** in memory (`llama3.1:8b`: 5.6 GB, `nomic-embed-text`: 323 MB). There was no model unloading between the embedder and LLM.",
        "   - A dedicated re-measurement of warm latency on 30 test tickets with both embedding cache and LLM cache disabled showed median latencies of **2693.1 ms** (hashing) vs **2676.9 ms** (nomic), difference: **-16.2 ms** (p95: 3709.3 ms vs 3556.3 ms). The elevated warm latency observed in the saved 120-ticket test run (+2394.0 ms) had an unknown cause.",
        "",
        "---",
        "",
        "## 5. Run-to-Run Variability",
        "",
        "The baseline `llm-rag-hashing` was re-run on the same 120 test tickets with identical generation settings ($T=0, \\text{seed}=42$) and caches disabled:",
        "",
        "| Endpoint | Run 1 (Pre-Registered Baseline) | Run 2 (Re-Run) | Discordant Pairs ($b$, $c$) | Exact McNemar $p$-value |",
        "| :--- | :---: | :---: | :---: | :---: |",
        f"| **Category Accuracy** | **{cat_acc_h*100:.1f}%** ({sum(corr_cat_h)}/120) | **{sum(corr_cat_rerun)/120*100:.1f}%** ({sum(corr_cat_rerun)}/120) | $b={b_cat_12}, c={c_cat_12}$ ({b_cat_12+c_cat_12} discordant) | $p = {p_cat_12:.6f}$ |",
        f"| **Priority Accuracy** | **{prio_acc_h*100:.1f}%** ({sum(corr_prio_h)}/120) | **{sum(corr_prio_rerun)/120*100:.1f}%** ({sum(corr_prio_rerun)}/120) | $b={b_prio_12}, c={c_prio_12}$ ({b_prio_12+c_prio_12} discordant) | $p = {p_prio_12:.6f}$ |",
        "",
        f"- Across the 120 tickets, **{diff_any_12}/120 tickets changed outputs** between Run 1 and Run 2 ({diff_cat_12} category, {diff_prio_12} priority).",
        f"- The priority accuracy difference between nomic and hashing ($b={b_prio}, c={c_prio}$, {b_prio+c_prio} discordant pairs) is of the same order as this run-to-run noise.",
        "- The cause of the non-determinism was not investigated.",
        "- The run-2 per-ticket file was reconstructed from the saved run log (task log), not written by the benchmark itself.",
        "",
        "---",
        "",
        "## 6. Pre-Registered Decision Rule Evaluation",
        "",
        f"1. **Condition 1 (Primary Endpoint Improvement)**: **{'PASS' if cond1_pass else 'FAIL'}**",
        f"   - Priority accuracy improved by +{prio_diff_pp:.1f} pp (threshold: >= +5.0 pp), but $p = {p_prio:.6f}$ (required: $p < 0.025$). Category accuracy was {cat_diff_pp:+.1f} pp ($p = {p_cat:.6f}$).",
        f"2. **Condition 2 (No Non-Inferiority Breach)**: **{'PASS' if cond2_pass else 'FAIL'}**",
        f"   - Category accuracy was {cat_diff_pp:+.1f} pp (threshold: >= -2.0 pp). Priority accuracy was {prio_diff_pp:+.1f} pp (threshold: >= -2.0 pp).",
        f"3. **Condition 3 (Injection Robustness)**: **{'PASS' if cond3_pass else 'FAIL'}**",
        f"   - Pooled attack successes: nomic={pooled_n_succ}/60 vs hashing={pooled_h_succ}/60 (threshold: nomic <= hashing + 1, i.e. <= {pooled_h_succ + 1}; Fisher exact two-sided $p = {p_fisher:.4f}$). Observed: {pooled_n_succ} {'<=' if cond3_pass else '>'} {pooled_h_succ + 1}.",
        f"4. **Condition 4 (Warm Latency Overhead)**: **{'PASS' if cond4_pass else 'FAIL'}**",
        f"   - Median warm latency difference in saved test run: {lat_diff_ms:+.1f} ms (threshold: at most +150 ms). Overhead is {lat_diff_ms:.1f} ms (though 30-ticket re-measurement showed -16.2 ms diff).",
        "",
        "---",
        "",
        "## 7. Final Decision",
        "",
        f"**Decision**: **Examples stay on `hashing-v2`**.",
        "",
        f"Conditions 1, 3, and 4 failed under the pre-registered decision rules. While nomic-retrieved examples produced a descriptive gain in exact priority accuracy (+5.8 pp), the result does not meet the pre-registered significance threshold ($p = {p_prio:.4f} > 0.025$). For prompt injection, pooled held-out attack successes were {pooled_n_succ}/60 for nomic vs {pooled_h_succ}/60 for hashing (two-sided Fisher exact $p = {p_fisher:.4f}$), which fails Condition 3 (threshold: nomic $\\le$ hashing + 1). Warm latency overhead in the main run (+2394 ms) also failed Condition 4 (cause undetermined; re-measurement on 30 tickets showed no overhead).",
        "",
        "In accordance with the pre-registration protocol, this outcome is reported as **\"no evidence of benefit\"**, not as proof of no difference ($N=120$ has low statistical power for small effects).",
        "",
    ]

    report_path = Path("benchmarks") / "RAG_NOMIC.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Generated {report_path} successfully.")


if __name__ == "__main__":
    main()
