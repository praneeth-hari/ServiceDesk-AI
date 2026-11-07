# Free Local Dense Embeddings Evaluation Report (Ollama `nomic-embed-text`)

Evaluation of automated ticket triage using local dense embeddings powered by Ollama's `nomic-embed-text` as a kNN retrieval method on the **ServiceDesk600** dataset (`data/servicedesk600`, $N=600$) and prompt-injection benchmark suites ($N=40, 30, 30$).

---

## 1. Method & Technical Architecture

### Model & Runtime Specification
- **Model**: `nomic-embed-text` (137M parameters, nomic-bert architecture)
- **Dimensionality**: 768-dimensional unit-length vectors (float32, L2-normalized)
- **Local Runtime**: Ollama REST API (`/api/embed`) running at `http://localhost:11434`
- **Server Version**: `0.34.3`
- **Model Digest**: `0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f`
- **Decision Rule & Hyperparameters**: Cosine similarity $k$-Nearest Neighbours ($k=5$, $\text{min\_similarity}=0.12$, similarity-weighted voting, majority class fallback on empty neighbourhood).
  - **Note on $k$ and $\text{min\_similarity}$**: All kNN retrieval methods (`hashing-knn`, `minilm-knn`, `bge-small-knn`, and `nomic-knn`) evaluate under the **identical** configuration: $k=5$ and $\text{min\_similarity}=0.12$. These hyperparameters are the pre-existing system defaults defined in `app.services.triage` and were **not** tuned or selected using the test set.

### Deterministic Disk Cache
Embeddings are deterministically persisted in a local SQLite cache (`.cache/embeddings/cache.sqlite3`, gitignored). Every cache entry is keyed by:
$$\text{key} = \text{SHA-256}(\text{model\_name} \parallel \text{model\_digest} \parallel \text{prefix} \parallel \text{SHA-256}(\text{text}))$$
This guarantees that repeated benchmark runs or evaluations across identical ticket texts are bitwise deterministic, while invalidating entries automatically if the underlying model digest or task prefix changes.

---

## 2. Prefix Variant Selection (5-Fold CV on `train.jsonl` Only, $N=480$)

Nomic Embed Text requires task-specific prefixes to condition the embedding representation. To adhere strictly to scientific generalization rules, candidate variants were evaluated solely on the training split (`data/servicedesk600/train.jsonl`, $N=480$) using 5-fold cross-validation without touching `test.jsonl`:

| Prefix Variant | Stored (Doc) Prefix | Query Prefix | Category Acc [95% CI] | Cat Macro-F1 | Priority Acc [95% CI] | Priority Within-One | Combined Acc |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **`classification`** | `classification: ` | `classification: ` | **71.25%** [67.0%, 75.1%] | **0.7039** | **57.50%** [53.0%, 61.9%] | **89.58%** | **40.62%** |
| `clustering` | `clustering: ` | `clustering: ` | 70.62% [66.4%, 74.5%] | 0.6976 | 54.37% [49.9%, 58.8%] | 89.17% | 38.75% |
| `none` | `(none)` | `(none)` | 70.42% [66.2%, 74.3%] | 0.6934 | 53.54% [49.1%, 57.9%] | 87.50% | 37.29% |
| `search` | `search_document: ` | `search_query: ` | 65.62% [61.3%, 69.7%] | 0.6436 | 47.92% [43.5%, 52.4%] | 85.83% | 31.87% |

> **Variant Selection Decision**: `classification` achieved the top cross-validation accuracy across category, macro-F1, priority, and combined metrics. It was frozen in code as the default prefix variant.

---

## 3. Triage Benchmark Evaluation on Test Split ($N=120$)

Below is the verified comparison across the saved result JSON files (`benchmarks/results/hashing-knn.json`, `benchmarks/results/minilm-knn.json`, and `benchmarks/results_retrieval/nomic-knn.json`):

| Method | Category Acc [95% CI] | Cat Macro-F1 | Priority Acc [95% CI] | Priority Within-One | Hard-Ticket Cat Acc | Mean Latency / Ticket | Invalid Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`nomic-knn`** | 78.3% [70.2%, 84.8%] | 0.7753 | 50.0% [41.2%, 58.8%] | 85.0% | 66.7% (20/30) | 14.9 ms (uncached) | 0.0% |
| **`minilm-knn`** | 76.7% [68.3%, 83.3%] | 0.7571 | 47.5% [38.8%, 56.4%] | 85.0% | 70.0% (21/30) | 0.9 ms | 0.0% |
| **`hashing-knn`** | 62.5% [53.6%, 70.7%] | 0.6100 | 44.2% [35.6%, 53.1%] | 81.7% | 56.7% (17/30) | 1.1 ms | 0.0% |

### Key Mapping & Provenance
Every column in the table above is fed directly from the corresponding JSON keys:
- **Category Acc**: `metrics.category_metrics.accuracy` and `metrics.category_metrics.ci_95`
- **Cat Macro-F1**: `metrics.category_metrics.macro_f1`
- **Priority Acc**: `metrics.priority_metrics.accuracy` and `metrics.priority_metrics.ci_95`
- **Priority Within-One**: `metrics.priority_metrics.within_one_accuracy`
- **Hard-Ticket Cat Acc**: `metrics.category_metrics.hard_accuracy` and `metrics.category_metrics.hard_count`
- **Mean Latency**: `mean_latency_ms` (for `nomic-knn`, the realistic per-ticket end-to-end uncached latency including embedding call is 14.9 ms; the in-memory SQLite cache lookup latency is 1.2 ms).

### Explanation of Table Reconciliation
The committed files `benchmarks/results/hashing-knn.json` and `benchmarks/results/minilm-knn.json` (and `benchmarks/RESULTS.md`) are the canonical source of truth:
- For `hashing-knn`: `within_one_accuracy` is **81.7%** (98/120) and `hard_accuracy` is **56.7%** (17/30).
- For `minilm-knn`: `within_one_accuracy` is **85.0%** (102/120) and `hard_accuracy` is **70.0%** (21/30).
- An earlier draft inadvertently misquoted these numbers as 76.67% and 46.67% (hashing) and 83.33% and 60.0% (minilm). The generated table above faithfully reflects the exact values from the saved JSON files.

### Statistical Significance (Exact Two-Sided McNemar Tests)
Evaluated on the exact paired predictions ($N=120$) from `benchmarks/results/` and `benchmarks/results_retrieval/` joined against `data/servicedesk600/test.jsonl`:

| Comparison | Metric | Discordant Pairs (A correct, B wrong) | Discordant Pairs (A wrong, B correct) | Total Discordant ($n$) | Exact Two-Sided $p$-value | Statistically Significant ($\alpha=0.05$)? |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| `nomic-knn` vs `hashing-knn` | Category | 25 | 6 | 31 | 0.000878 | **Yes ($p < 0.001$)** |
| `nomic-knn` vs `hashing-knn` | Priority | 19 | 12 | 31 | 0.281042 | No ($p = 0.281$) |
| `nomic-knn` vs `hashing-knn` | Combined | 28 | 9 | 37 | 0.002563 | **Yes ($p < 0.01$)** |
| `nomic-knn` vs `minilm-knn` | Category | 11 | 9 | 20 | 0.823803 | No ($p = 0.824$) |
| `nomic-knn` vs `minilm-knn` | Priority | 11 | 8 | 19 | 0.647606 | No ($p = 0.648$) |
| `nomic-knn` vs `minilm-knn` | Combined | 17 | 10 | 27 | 0.247789 | No ($p = 0.248$) |

---

## 4. Prompt Injection Robustness Benchmark

Adversarial prompt injection evaluations across all three benchmark sets (`dev`, `heldout_v1`, `heldout_v2`):

### Overall Attack Success Rate (Side-by-Side):

| Dataset Split | $N$ | `hashing-knn` Overall ASR [95% CI] | `nomic-knn` Overall ASR [95% CI] |
| :--- | :---: | :---: | :---: |
| **Dev Set** | 40 | 1/40 (2.5%) [0.4%, 12.9%] | 2/40 (5.0%) [1.4%, 16.5%] |
| **Held-Out v1** | 30 | 6/30 (20.0%) [9.5%, 37.3%] | 5/30 (16.7%) [7.3%, 33.6%] |
| **Independent Held-Out v2** | 30 | 4/30 (13.3%) [5.3%, 29.7%] | 2/30 (6.7%) [1.8%, 21.3%] |

### Attack Success by Family (Counts & Successes):

#### Held-Out v2 ($N=30$):
| Attack Family | $n$ | `hashing-knn` ASR | `nomic-knn` ASR |
| :--- | :---: | :---: | :---: |
| `delimiter_breaking` | 3 | 0/3 (0.0%) | 0/3 (0.0%) |
| `fake_agent_note` | 3 | 0/3 (0.0%) | 0/3 (0.0%) |
| `fake_previous_result` | 3 | 0/3 (0.0%) | 0/3 (0.0%) |
| `instruction_override` | 3 | 0/3 (0.0%) | 0/3 (0.0%) |
| **`lexical_stuffing`** | 5 | 4/5 (80.0%) | 1/5 (20.0%) |
| `obfuscated` | 3 | 0/3 (0.0%) | 0/3 (0.0%) |
| `polite_request` | 4 | 0/4 (0.0%) | 1/4 (25.0%) |
| `priority_inflation` | 3 | 0/3 (0.0%) | 0/3 (0.0%) |
| `role_impersonation` | 3 | 0/3 (0.0%) | 0/3 (0.0%) |

#### Held-Out v1 ($N=30$):
| Attack Family | $n$ | `hashing-knn` ASR | `nomic-knn` ASR |
| :--- | :---: | :---: | :---: |
| `delimiter_breaking` | 3 | 1/3 (33.3%) | 1/3 (33.3%) |
| `fake_agent_note` | 3 | 0/3 (0.0%) | 0/3 (0.0%) |
| `fake_label` | 3 | 0/3 (0.0%) | 1/3 (33.3%) |
| `fake_previous_result` | 3 | 0/3 (0.0%) | 1/3 (33.3%) |
| `instruction_override` | 3 | 0/3 (0.0%) | 1/3 (33.3%) |
| **`lexical_stuffing`** | 3 | 3/3 (100.0%) | 0/3 (0.0%) |
| `obfuscated` | 3 | 0/3 (0.0%) | 0/3 (0.0%) |
| `polite_request` | 3 | 1/3 (33.3%) | 0/3 (0.0%) |
| `priority_inflation` | 3 | 1/3 (33.3%) | 1/3 (33.3%) |
| `role_impersonation` | 3 | 0/3 (0.0%) | 0/3 (0.0%) |

#### Dev Set ($N=40$):
| Attack Family | $n$ | `hashing-knn` ASR | `nomic-knn` ASR |
| :--- | :---: | :---: | :---: |
| `delimiter_breaking` | 7 | 0/7 (0.0%) | 0/7 (0.0%) |
| `fake_label` | 7 | 0/7 (0.0%) | 0/7 (0.0%) |
| `instruction_override` | 7 | 0/7 (0.0%) | 1/7 (14.3%) |
| `obfuscated` | 6 | 0/6 (0.0%) | 0/6 (0.0%) |
| `priority_inflation` | 6 | 0/6 (0.0%) | 0/6 (0.0%) |
| `role_impersonation` | 7 | 1/7 (14.3%) | 1/7 (14.3%) |

### Statistical Analysis of Injection Findings
1. **`lexical_stuffing` in Held-Out v2 ($n=5$)**:
   - `hashing-knn`: 4/5 (80.0%) attack successes
   - `nomic-knn`: 1/5 (20.0%) attack successes
   - **Two-sided Fisher Exact Test**: $p = 0.2063$.
   - **Interpretation**: Because $n = 5$, the observed difference is **not statistically significant** at the $\alpha = 0.05$ level ($p = 0.2063 > 0.05$). While `nomic-knn` showed fewer keyword-stuffing successes in this small sample, a larger test suite is required before claiming a significant robustness advantage.
2. **Overall Held-Out v2 Attack Success Rate ($N=30$)**:
   - Paired discordant pairs on overall attack outcome: $b = 1$ (nomic succeeded, hashing failed), $c = 3$ (nomic failed, hashing succeeded).
   - **Paired Exact McNemar Test**: $p = 0.6250$. The difference in overall attack success between `nomic-knn` (2/30) and `hashing-knn` (4/30) is not statistically significant.

---

## 5. Reproduction Commands

```bash
# 1. Ensure Ollama is running and nomic-embed-text is pulled
ollama pull nomic-embed-text

# 2. Run 5-fold cross-validation variant selection on the training split only (N=480)
python -m app.scripts.select_nomic_variant --output-dir benchmarks/results_retrieval

# 3. Evaluate frozen nomic-knn on the held-out test split (N=120)
python -m app.scripts.benchmark_triage --methods nomic-knn --output-dir benchmarks/results_retrieval

# 4. Evaluate prompt injection on Dev Set (N=40)
python -m app.scripts.benchmark_injection --methods nomic-knn --dataset-path data/injection/injection_set.jsonl --output-dir benchmarks/results_retrieval/injection_dev

# 5. Evaluate prompt injection on Held-Out v1 Set (N=30)
python -m app.scripts.benchmark_injection --methods nomic-knn --dataset-path data/injection/heldout_set.jsonl --output-dir benchmarks/results_retrieval/injection_heldout

# 6. Evaluate prompt injection on Independent Held-Out v2 Set (N=30)
python -m app.scripts.benchmark_injection --methods nomic-knn --dataset-path data/injection/heldout_v2.jsonl --output-dir benchmarks/results_retrieval/injection_heldout_v2
```

---

## 6. Limitations & Caveats

1. **Ollama Co-Location & Model Swapping**: Not tested with the LLM model (e.g. `llama3` or `qwen2.5`) and the embedding model loaded together in one Ollama instance. Co-locating both models in memory may induce GPU VRAM contention or sequential model swapping latency if Ollama unloads the embedder to serve chat completions.
2. **Latency Measurement**: The "cached" latency (1.2 ms) measures SQLite lookup and is not a realistic per-ticket production figure for new tickets. The uncached latency of **14.9 ms** per ticket represents the true inference cost including the local HTTP API embedding call.
3. **Small Injection Sample Sizes**: Held-out attack sets contain $N=30$ tickets ($n=3$ to $5$ per family). As demonstrated by the Fisher exact test ($p = 0.2063$), individual family metrics have wide confidence intervals and observed differences cannot be certified as statistically significant on these sample sizes.
4. **Synthetic Data**: ServiceDesk600 is synthetically curated. Production ticketing logs exhibit greater variance in vocabulary, shorthand, and multi-language interactions.

---

## 7. Conclusion

`nomic-knn` is significantly better than `hashing-knn` on category and combined accuracy, statistically indistinguishable from `minilm-knn`, needs only Ollama, and shows fewer keyword-stuffing successes in a small sample.

Overall injection robustness is similar: hashing-knn 11/100 and nomic-knn 9/100 attack successes pooled over the dev, held-out v1 and held-out v2 sets (v1 is not independent). The difference is concentrated in keyword stuffing (held-out sets pooled: hashing 7/8, nomic 1/8; pooled after the fact, small n; Fisher p=0.206 on v2 alone; the dev set has 0 lexical_stuffing tickets, so the pooled figure is post hoc). nomic-knn showed one success each in several instruction-style families (polite_request, fake_label, fake_previous_result, instruction_override), where hashing-knn mostly had none (n tiny). Dense retrieval does not remove the need for the LLM-mode defenses.
