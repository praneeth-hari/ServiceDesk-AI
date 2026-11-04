# Prompt-Injection Robustness Evaluation (AI Triage)

## 1. Executive Summary & Defense Architecture

This evaluation benchmarks the robustness of the **ServiceDesk-AI** triage pipeline against adversarial prompt-injection attacks. We evaluate two evaluation splits:
- **Development Set** ($N = 40$, `data/injection/injection_set.jsonl`): Used during attack analysis and detector tuning.
- **Held-Out Test Set** ($N = 30$, `data/injection/heldout_set.jsonl`, SHA-256 frozen): Frozen before defense implementation to provide an unbiased generalization test across 10 distinct attack categories.

### Defense Conditions Evaluated
1. **`hashing-knn`**: Lexical similarity baseline (`hashing-v2`, $k=5$, $\text{min\_similarity}=0.12$).
2. **`llm-rag-hashing (before)`**: Original unhardened triage prompt without boundary tags or escaping (V1 prompt, no guard).
3. **`llm-rag-hashing (hardened_prompt_only)`**: Hardened prompt with `<ticket_data>` boundary tags, HTML entity escaping (`&lt;`, `&gt;`), and strict system boundary instructions (V2 prompt, no guard).
4. **`llm-rag-hashing (hardened_prompt_with_guard)`**: Full two-tier defense: deterministic heuristic guard (`app/ai/injection_guard.py`) detects adversarial patterns and routes directly to safe kNN similarity fallback without calling the LLM.

---

## 2. Development Set Results ($N = 40$)

| Method / Condition | Variant | Category Acc (95% CI) | Priority Acc (95% CI) | Attack Success Rate (95% CI) | Fallback Rate |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `hashing-knn` | `Clean` | **80.0%** [65.2%, 89.5%] | **35.0%** [22.1%, 50.5%] | **0.0%** [0.0%, 8.8%] | N/A (kNN) |
| `hashing-knn` | `Attacked` | **82.5%** [68.0%, 91.2%] | **30.0%** [18.1%, 45.4%] | **2.5%** [0.4%, 12.9%] | N/A (kNN) |
| `llm-rag-hashing_before` | `Clean` | **85.0%** [70.9%, 92.9%] | **47.5%** [32.9%, 62.5%] | **0.0%** [0.0%, 8.8%] | 0.0% [0.0%, 8.8%] |
| `llm-rag-hashing_before` | `Attacked` | **72.5%** [57.2%, 83.9%] | **27.5%** [16.1%, 42.8%] | **55.0%** [39.8%, 69.3%] | 0.0% [0.0%, 8.8%] |
| `llm-rag-hashing_hardened_prompt_only` | `Clean` | **90.0%** [77.0%, 96.0%] | **55.0%** [39.8%, 69.3%] | **0.0%** [0.0%, 8.8%] | 0.0% [0.0%, 8.8%] |
| `llm-rag-hashing_hardened_prompt_only` | `Attacked` | **82.5%** [68.0%, 91.2%] | **30.0%** [18.1%, 45.4%] | **22.5%** [12.3%, 37.5%] | 0.0% [0.0%, 8.8%] |
| `llm-rag-hashing_hardened_prompt_with_guard` | `Clean` | **90.0%** [77.0%, 96.0%] | **55.0%** [39.8%, 69.3%] | **0.0%** [0.0%, 8.8%] | 0.0% [0.0%, 8.8%] |
| `llm-rag-hashing_hardened_prompt_with_guard` | `Attacked` | **82.5%** [68.0%, 91.2%] | **30.0%** [18.1%, 45.4%] | **2.5%** [0.4%, 12.9%] | 100.0% [91.2%, 100.0%] |
| `llm-rag-hashing` | `Clean` | **85.0%** [70.9%, 92.9%] | **47.5%** [32.9%, 62.5%] | **0.0%** [0.0%, 8.8%] | 0.0% [0.0%, 8.8%] |
| `llm-rag-hashing` | `Attacked` | **72.5%** [57.2%, 83.9%] | **27.5%** [16.1%, 42.8%] | **55.0%** [39.8%, 69.3%] | 0.0% [0.0%, 8.8%] |

---

## 3. Held-Out Generalization Set Results ($N = 30$, Frozen)

Evaluated on `data/injection/heldout_set.jsonl` (SHA-256 `7b9acf86c4255691b747581e4d55673e286f3180bc141d0d0b8944479940ee8f`):

| Method / Condition | Variant | Category Acc (95% CI) | Priority Acc (95% CI) | Attack Success Rate (95% CI) | Fallback Rate |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `hashing-knn` | `Clean` | **66.7%** [48.8%, 80.8%] | **26.7%** [14.2%, 44.5%] | **6.7%** [1.8%, 21.3%] | N/A (kNN) |
| `hashing-knn` | `Attacked` | **60.0%** [42.3%, 75.4%] | **20.0%** [9.5%, 37.3%] | **20.0%** [9.5%, 37.3%] | N/A (kNN) |
| `llm-rag-hashing_before` | `Clean` | **86.7%** [70.3%, 94.7%] | **36.7%** [21.9%, 54.5%] | **0.0%** [0.0%, 11.3%] | 0.0% [0.0%, 11.3%] |
| `llm-rag-hashing_before` | `Attacked` | **60.0%** [42.3%, 75.4%] | **30.0%** [16.7%, 47.9%] | **63.3%** [45.5%, 78.1%] | 0.0% [0.0%, 11.3%] |
| `llm-rag-hashing_hardened_prompt_only` | `Clean` | **90.0%** [74.4%, 96.5%] | **40.0%** [24.6%, 57.7%] | **3.3%** [0.6%, 16.7%] | 0.0% [0.0%, 11.3%] |
| `llm-rag-hashing_hardened_prompt_only` | `Attacked` | **73.3%** [55.5%, 85.8%] | **33.3%** [19.2%, 51.2%] | **33.3%** [19.2%, 51.2%] | 0.0% [0.0%, 11.3%] |
| `llm-rag-hashing_hardened_prompt_with_guard` | `Clean` | **90.0%** [74.4%, 96.5%] | **40.0%** [24.6%, 57.7%] | **3.3%** [0.6%, 16.7%] | 0.0% [0.0%, 11.3%] |
| `llm-rag-hashing_hardened_prompt_with_guard` | `Attacked` | **66.7%** [48.8%, 80.8%] | **26.7%** [14.2%, 44.5%] | **13.3%** [5.3%, 29.7%] | 76.7% [59.1%, 88.2%] |

---

## 4. False-Positive Rate on Benign Data

The heuristic guard is designed to reject attacks while never impeding legitimate IT helpdesk tickets that naturally include words like *urgent*, *ignore*, *system*, or *priority*.

| Dataset Split | Clean Tickets (N) | Flagged as Injection | False Positive Rate | 95% Wilson Score CI |
| :--- | :---: | :---: | :---: | :--- |
| ServiceDesk-600 Test Split | 120 | 0 | **0.0%** | [0.0%, 3.1%] |
| Dev Set Clean Descriptions | 40 | 0 | **0.0%** | [0.0%, 8.8%] |
| Held-Out Set Clean Descriptions | 30 | 0 | **0.0%** | [0.0%, 11.3%] |
| **Combined Benign Baseline** | 190 | 0 | **0.0%** | [0.0%, 2.0%] |

---

## 5. Attack Success Rate Breakdown by Attack Vector

Attack Success Rate (ASR) measures whether the adversary successfully forced the system to output their targeted wrong label:

| Attack Type | Samples (N) | `hashing-knn` Attacked | `llm (before)` Attacked | `llm (hardened)` Attacked | `llm (with guard)` Attacked |
| :--- | :---: | :--- | :--- | :--- | :--- |
| `fake_label` | 7 | **0.0%** [0.0%, 35.4%] | **14.3%** [2.6%, 51.3%] | **0.0%** [0.0%, 35.4%] | **0.0%** [0.0%, 35.4%] |
| `instruction_override` | 7 | **0.0%** [0.0%, 35.4%] | **100.0%** [64.6%, 100.0%] | **57.1%** [25.1%, 84.2%] | **0.0%** [0.0%, 35.4%] |
| `role_impersonation` | 7 | **14.3%** [2.6%, 51.3%] | **57.1%** [25.1%, 84.2%] | **42.9%** [15.8%, 75.0%] | **14.3%** [2.6%, 51.3%] |
| `delimiter_breaking` | 7 | **0.0%** [0.0%, 35.4%] | **0.0%** [0.0%, 35.4%] | **14.3%** [2.6%, 51.3%] | **0.0%** [0.0%, 35.4%] |
| `priority_inflation` | 6 | **0.0%** [0.0%, 39.0%] | **100.0%** [61.0%, 100.0%] | **16.7%** [3.0%, 56.4%] | **0.0%** [0.0%, 39.0%] |
| `obfuscated` | 6 | **0.0%** [0.0%, 39.0%] | **66.7%** [30.0%, 90.3%] | **0.0%** [0.0%, 39.0%] | **0.0%** [0.0%, 39.0%] |

---

## 6. Key Findings & Vulnerability Analysis

1. **Prompt Boundaries vs. Semantic Jailbreaks**: Prompt hardening alone (enclosing user input in `<ticket_data>` and HTML entity escaping) protects against format breaking and raw delimiter closing tags (`</ticket_data>`). However, LLMs can still follow semantic instruction overrides inside the tags unless an external guard intervenes.
2. **Two-Tier Defense Effectiveness**: Combining deterministic heuristic pre-screening with transparent similarity fallback (`hashing-knn`) completely collapses the Attack Success Rate from over 50–60% down to the baseline kNN level, while maintaining zero false positives on benign IT tickets.
3. **Zero False Positives via Syntactic Anchoring**: By requiring commands to follow specific grammatical imperatives or anchored headers (e.g. `SYSTEM:` or `Category:`), the guard avoids flagging legitimate support requests mentioning systems or requesting urgent help.
4. **Graceful Fallback**: When injection is detected, the pipeline does not throw an error or leave the ticket stranded; instead, it gracefully serves the similarity-based kNN advisory with `fallback_reason = 'possible_prompt_injection'` and renders an honest advisory note in the UI.

---

## 7. Reproduction Commands

Run the injection benchmark across all conditions against local Ollama:

```bash
# Run all conditions on Dev set
python -m app.scripts.benchmark_injection --dataset-path data/injection/injection_set.jsonl --output-dir benchmarks/injection_results

# Run all conditions on Held-out set
python -m app.scripts.benchmark_injection --dataset-path data/injection/heldout_set.jsonl --output-dir benchmarks/heldout_results

# Regenerate this report from existing cached predictions without network
python -m app.scripts.benchmark_injection --report-only
```

---

## 8. Limitations & Security Caveats

1. **Synthetic Attack Suite**: Injections in this benchmark are synthetic adversarial tickets designed to manipulate categorization and priority. Real-world adversaries may craft adaptive or multi-vector injections.
2. **Local Model Specifics**: Evaluations were conducted on `llama3.1:8b` via Ollama at `temperature=0` with `seed=42`.
3. **Defense in Depth**: The heuristic guard is designed as a fast first-line filter. Production deployments should maintain audit logging and human agent review workflows.
