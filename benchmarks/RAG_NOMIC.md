# RAG Retrieval Benchmark: Nomic-Retrieved vs Hashing-Retrieved Examples

Evaluation of in-context example retrieval for LLM triage (`llama3.1:8b`) on the **ServiceDesk600** dataset ($N=120$ test split) and prompt-injection robustness on frozen held-out attack suites ($N=30$ v1, $N=30$ v2, pooled $N=60$).

**Pre-registration SHA-256**: `c79b013a9dd632eefe7c59b01119c365b2d43b56dffad26fd8af1792bbbfffc7` (file: `benchmarks/RAG_NOMIC_PREREG.md`).

---

## 1. Primary & Secondary Triage Endpoints (Test Split, N=120)

| Metric | `llm-rag-hashing` (Baseline) | `llm-rag-nomic` | Difference (Nomic - Baseline) |
| :--- | :---: | :---: | :---: |
| **Category Accuracy (Primary)** | **85.8%** (103/120) [78.5%, 91.0%] | **84.2%** (101/120) [76.6%, 89.6%] | -1.7 pp |
| **Priority Accuracy (Primary)** | **64.2%** (77/120) [55.3%, 72.2%] | **70.0%** (84/120) [61.3%, 77.5%] | +5.8 pp |
| Category Macro-F1 | 0.8584 | 0.8385 | -0.0199 |
| Hard-Ticket Category Acc ($n=30$) | 70.0% (21/30) | 73.3% (22/30) | +3.3 pp |
| Priority Within-One Acc | 96.7% (116/120) | 98.3% (118/120) | +1.7 pp |
| Cold First Request Latency | 16781.8 ms | 36932.8 ms | +20151.1 ms |
| Warm Median Latency | 2614.5 ms | 5008.5 ms | +2394.0 ms |
| Warm p95 Latency | 2840.9 ms | 7598.0 ms | +4757.2 ms |

---

## 2. Statistical Significance: Exact Two-Sided McNemar Tests

Significance evaluated on paired discordant pairs across the 120 test tickets with Bonferroni correction ($\alpha = 0.025$ per primary endpoint):

| Endpoint | Nomic Correct, Hashing Wrong ($b$) | Hashing Correct, Nomic Wrong ($c$) | Discordant Total ($b+c$) | Exact Two-Sided $p$-value | Significant at $\alpha = 0.025$? |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Category Accuracy** | 5 | 7 | 12 | **0.774414** | **No** |
| **Priority Accuracy** | 15 | 8 | 23 | **0.210040** | **No** |

- **Category Accuracy Analysis**: With $b = 5$ and $c = 7$ ($p = 0.774414$), there is no statistically detectable difference between hashing-retrieved and nomic-retrieved examples.
- **Priority Accuracy Analysis**: Although nomic improved priority accuracy by +5.8 percentage points ($b = 15, c = 8$), the difference does not reach statistical significance ($p = 0.210040 > 0.025$).

---

## 3. Prompt-Injection Robustness (Full Defenses: Hardened Prompt + Heuristic Guard)

Evaluated on held-out attack suites with full production defenses enabled. Baseline `llm-rag-hashing` numbers were re-run fresh in this session with `--no-resume`:

| Attack Set | Tickets ($N$) | `llm-rag-hashing` Attack Successes (ASR) | `llm-rag-nomic` Attack Successes (ASR) | Difference |
| :--- | :---: | :---: | :---: | :---: |
| **Held-Out v1** | 30 | 4/30 (13.3%) | 6/30 (20.0%) | +6.7 pp |
| **Held-Out v2** | 30 | 2/30 (6.7%) | 3/30 (10.0%) | +3.3 pp |
| **Pooled (v1 + v2)** | 60 | **6/60 (10.0%)** | **9/60 (15.0%)** | **+5.0 pp** |

Two-sided Fisher exact test on pooled held-out injection: $p = 0.5822$ (odds ratio = 1.588).

---

## 4. LLM Generation Settings & Latency Measurement

1. **Generation Parameters**:
   - **Model**: `llama3.1:8b` (digest: `46e0c10c039e...`)
   - **Temperature**: `0.0`
   - **Seed**: `42`
   - **Output Format**: Enforced JSON schema (`OLLAMA_FORMAT_SCHEMA`) restricting `category` to 6 canonical categories and `priority` to 4 tiers.
2. **Latency Measurement & Model Co-Location**:
   - In the benchmark test runs, `latency_ms` measured the duration of `call_ollama_chat` per ticket. Nomic query embeddings were computed ahead of time in batch at startup.
   - Inspection with `ollama ps` right after a `llama3.1:8b` call and right after a `nomic-embed-text` embed call confirmed that **both models remain simultaneously loaded** in memory (`llama3.1:8b`: 5.6 GB, `nomic-embed-text`: 323 MB). There was no model unloading between the embedder and LLM.
   - A dedicated re-measurement of warm latency on 30 test tickets with both embedding cache and LLM cache disabled showed median latencies of **2693.1 ms** (hashing) vs **2676.9 ms** (nomic), difference: **-16.2 ms** (p95: 3709.3 ms vs 3556.3 ms). The elevated warm latency observed in the saved 120-ticket test run (+2394.0 ms) had an unknown cause.

---

## 5. Run-to-Run Variability

The baseline `llm-rag-hashing` was re-run on the same 120 test tickets with identical generation settings ($T=0, \text{seed}=42$) and caches disabled:

| Endpoint | Run 1 (Pre-Registered Baseline) | Run 2 (Re-Run) | Discordant Pairs ($b$, $c$) | Exact McNemar $p$-value |
| :--- | :---: | :---: | :---: | :---: |
| **Category Accuracy** | **85.8%** (103/120) | **85.0%** (102/120) | $b=1, c=2$ (3 discordant) | $p = 1.000000$ |
| **Priority Accuracy** | **64.2%** (77/120) | **62.5%** (75/120) | $b=5, c=7$ (12 discordant) | $p = 0.774414$ |

- Across the 120 tickets, **17/120 tickets changed outputs** between Run 1 and Run 2 (4 category, 13 priority).
- The priority accuracy difference between nomic and hashing ($b=15, c=8$, 23 discordant pairs) is of the same order as this run-to-run noise.
- The cause of the non-determinism was not investigated.
- The run-2 per-ticket file was reconstructed from the saved run log (task log), not written by the benchmark itself.

---

## 6. Pre-Registered Decision Rule Evaluation

1. **Condition 1 (Primary Endpoint Improvement)**: **FAIL**
   - Priority accuracy improved by +5.8 pp (threshold: >= +5.0 pp), but $p = 0.210040$ (required: $p < 0.025$). Category accuracy was -1.7 pp ($p = 0.774414$).
2. **Condition 2 (No Non-Inferiority Breach)**: **PASS**
   - Category accuracy was -1.7 pp (threshold: >= -2.0 pp). Priority accuracy was +5.8 pp (threshold: >= -2.0 pp).
3. **Condition 3 (Injection Robustness)**: **FAIL**
   - Pooled attack successes: nomic=9/60 vs hashing=6/60 (threshold: nomic <= hashing + 1, i.e. <= 7; Fisher exact two-sided $p = 0.5822$). Observed: 9 > 7.
4. **Condition 4 (Warm Latency Overhead)**: **FAIL**
   - Median warm latency difference in saved test run: +2394.0 ms (threshold: at most +150 ms). Overhead is 2394.0 ms (though 30-ticket re-measurement showed -16.2 ms diff).

---

## 7. Final Decision

**Decision**: **Examples stay on `hashing-v2`**.

Conditions 1, 3, and 4 failed under the pre-registered decision rules. While nomic-retrieved examples produced a descriptive gain in exact priority accuracy (+5.8 pp), the result does not meet the pre-registered significance threshold ($p = 0.2100 > 0.025$). For prompt injection, pooled held-out attack successes were 9/60 for nomic vs 6/60 for hashing (two-sided Fisher exact $p = 0.5822$), which fails Condition 3 (threshold: nomic $\le$ hashing + 1). Warm latency overhead in the main run (+2394 ms) also failed Condition 4 (cause undetermined; re-measurement on 30 tickets showed no overhead).

In accordance with the pre-registration protocol, this outcome is reported as **"no evidence of benefit"**, not as proof of no difference ($N=120$ has low statistical power for small effects).
