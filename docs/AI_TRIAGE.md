# AI Triage & Duplicate Detection

The AI layer provides automated, advisory category and priority suggestions as well as proactive duplicate ticket detection.

---

## How It Works

1. **Text Representation (Embeddings)**: When a ticket is created or updated, its `title` and `description` are embedded into a fixed-dimensional unit-norm (L2-normalized) numerical vector (`app/ai/embedder.py`).
2. **Fast Cosine Similarity**: Because all vectors are normalized to unit length (`||u||_2 = ||v||_2 = 1`), the cosine similarity between the query text and historical tickets reduces to an ultra-fast dot product:

   ```text
   cosine_similarity(u, v) = u . v
   ```

3. **Category & Priority Suggestion**:
   - Compares the issue against historically **resolved** and **closed** tickets with similarity >= `AI_MIN_SIMILARITY` (default: `0.12`).
   - Retrieves the top $k$ neighbours (`AI_KNN_K`, default: `5`).
   - Performs a similarity-weighted vote where each neighbour's weight equals its similarity score:

     ```text
     vote(category) = sum of the similarity of each neighbour with that category
     ```

   - Confidence is computed as the proportion of winning category weight over total neighbour weight:

     ```text
     confidence = vote(winning category) / sum of all neighbour similarities
     ```

   - Returns `null` suggestions with `confidence = 0.0` if no neighbours exceed the minimum similarity threshold.
4. **Duplicate Detection**:
   - Scans active, unresolved tickets (`open`, `in_progress`, `waiting_on_requester`) for high similarity (>= `AI_DUPLICATE_THRESHOLD`, default: `0.80`).
5. **Strict Privacy Isolation**:
   - Requesters **only** receive evidence items and possible duplicates from their own tickets (`requester_id == current_user.id`). They never see foreign ticket IDs, titles, or descriptions.
   - Category and priority votes aggregate across the entire knowledge base without leaking individual ticket details.
6. **Advisory by Design**: Suggestions never automatically mutate a ticket. They guide agents and requesters while keeping humans firmly in control. Failure of the AI layer never prevents ticket creation or updates.

---

## Endpoints

- `POST /api/v1/triage/suggest`: Computes advisory category/priority suggestions and duplicate candidates from `title` and `description` for any authenticated user.
- `GET /api/v1/tickets/{id}/similar`: Returns similar tickets to an existing ticket, excluding itself. Restricted to `agent` and `admin` roles (returns 403 for requesters, 404 if ticket does not exist; optional `?limit=` between 1 and 20).

---

## Configuration Settings

| Setting | Default | Description |
| :--- | :--- | :--- |
| `AI_EMBEDDER` | `"hashing"` | Active embedding backend. Valid values are `"hashing"` (default, stored in the database as model name `"hashing-v2"`) and `"sbert"`. |
| `AI_DUPLICATE_THRESHOLD` | `0.80` | Minimum cosine similarity to flag an unresolved ticket as a duplicate. |
| `AI_MIN_SIMILARITY` | `0.12` | Minimum cosine similarity required to participate in kNN voting. |
| `AI_KNN_K` | `5` | Number of nearest neighbours used for category/priority voting. |
| `AI_MAX_CANDIDATES` | `5000` | Maximum candidate pool loaded for similarity ranking. |

---

## Optional Dense Embedder (Sentence-Transformers)

The default `hashing-v2` backend requires zero downloads or external model weights. sbert is supported as an optional pluggable embedder (requirements-ai.txt) but has not been measured on this dataset:

```powershell
pip install -r requirements-ai.txt
```

To use it, set `AI_EMBEDDER=sbert` in `.env`.

---

## Benchmark & Evaluation

Evaluation is performed via `app/scripts/eval_triage.py` on a synthetic evaluation dataset (`data/triage_eval.csv`, 120 synthetic tickets balanced across all 6 categories):

```powershell
# Standard evaluation on held-out test split (24 tickets)
python -m app.scripts.eval_triage

# Run 5-fold cross-validation sweep on train split only, then evaluate test split
python -m app.scripts.eval_triage --tune
```

> [!NOTE]
> The metrics and parameter sweeps below reflect measurements on the earlier small evaluation set (`data/triage_eval.csv`, N=24 held-out test tickets). For the current comprehensive 600-ticket benchmark (ServiceDesk-600) comparing lexical kNN, dense sentence transformers, and LLM zero-shot / RAG, see [AI triage evaluation in README.md](../README.md#ai-triage-evaluation) and [benchmarks/RESULTS.md](../benchmarks/RESULTS.md).
>
> The evaluation dataset `data/triage_eval.csv` is strictly synthetic benchmark demo data. The test split is never used for parameter tuning.

### 5-Fold Cross-Validation on Train Split Only (N=96)

Threshold tuning for `AI_MIN_SIMILARITY` was conducted via 5-fold stratified cross-validation exclusively on the 96 training tickets:

| `min_sim` | Coverage | Acc (when made) | Overall Acc (inc No Sugg) | Priority Overall |
| :--- | :--- | :--- | :--- | :--- |
| `0.05` | 100.0% | 59.5% | 59.5% | 33.6% |
| `0.08` | 100.0% | 59.5% | 59.5% | 33.6% |
| `0.10` | 100.0% | 59.5% | 59.5% | 33.6% |
| **`0.12`** *(chosen)* | **100.0%** | **60.6%** | **60.6%** | **33.6%** |
| `0.15` | 94.7% | 56.3% | 53.3% | 37.7% |
| `0.18` | 75.0% | 54.6% | 40.6% | 32.5% |
| `0.20` | 52.0% | 64.0% | 33.3% | 23.1% |
| `0.25` | 16.5% | 64.3% | 10.3% | 6.2% |
| `0.30` | 4.1% | 0.0% | 0.0% | 0.0% |

**Why `0.12` was selected**: On the training folds, `0.12` achieves 100% suggestion coverage while maximizing overall category accuracy at 60.6%. Higher thresholds like `0.20` drop coverage sharply (down to 52.0% coverage and 33.3% overall accuracy), rejecting viable suggestions as "no suggestion".

### Final Evaluation on Test Split (N=24, Earlier Small Evaluation Set)

| Metric | Before (`hashing`, sim=0.20) | After (`hashing-v2`, sim=0.12) | Random Chance | Majority Class |
| :--- | :--- | :--- | :--- | :--- |
| **Suggestion Coverage** | 16.67% (4/24) | **100.00%** (24/24) | — | — |
| **Category Accuracy (Overall)** | 16.67% (4/24) | **58.33%** (14/24) | 16.67% (1 of 6) | 16.67% (20/120) |
| **Category Acc (When Made)** | 16.67% (4/24) | **58.33%** (14/24) | 16.67% | 16.67% |
| **Priority Accuracy (Overall)** | 8.33% (2/24) | **37.50%** (9/24) | 25.00% (1 of 4) | 38.33% |
| **Priority Acc (When Made)** | 8.33% (2/24) | **37.50%** (9/24) | 25.00% | 38.33% |

**Per-Category Accuracy Breakdown (`hashing-v2`)**:

- `access`: **100.00%** (4/4)
- `hardware`: **75.00%** (3/4)
- `network`: **75.00%** (3/4)
- `email`: **50.00%** (2/4)
- `other`: **25.00%** (1/4)
- `software`: **25.00%** (1/4)


---

## AI Ticket Assist (Summary & Draft Reply)

The application supports an optional LLM-assisted workflow for support agents and administrators to quickly summarize complex tickets and generate draft replies directly on the ticket detail page.

### Core Principles

1. **Local-Only & Off by Default**: Powered exclusively by local Ollama (`AI_ASSIST_MODE=ollama`). When set to `off` (the default), no outgoing HTTP requests are made and the card displays a subtle inactive notice.
2. **Strict Privacy & Internal Notes Protection**:
   - Restricted to `agent` and `admin` roles (requesters receive HTTP 403 Forbidden).
   - Only public comments are included in the conversation history provided to the model. **Internal notes (`is_internal=True`) are strictly excluded** and never sent to Ollama.
   - All ticket fields and comments are wrapped in an untrusted `<ticket_data>` context block to protect against prompt injection.
   - Ephemeral and privacy-preserving: nothing is persisted to the database, and neither ticket content nor model outputs are ever logged.
3. **Advisory Drafts for Human Review**:
   - All AI draft replies are clearly tagged with "Draft only. Review before posting."
   - Clicking "Insert into reply" copies the draft into the reply composer without posting. Agents review and edit the draft before sending.
   - System prompts forbid resolution promises, SLA commitments, or requests for passwords and sensitive credentials.
4. **No Accuracy Claims**:
   - Assist outputs are conversational drafts and summaries to accelerate agent productivity, not categorical classifiers. No accuracy or benchmark claims are made.

### Configuration Settings

| Setting | Default | Description |
| :--- | :--- | :--- |
| `AI_ASSIST_MODE` | `"off"` | Assist mode: `"off"` (disabled) or `"ollama"` (active). |
| `AI_ASSIST_MODEL` | `"llama3.1:8b"` | Model tag for assist tasks (defaults to same model as triage). |
| `AI_ASSIST_TIMEOUT_SECONDS` | `60.0` | Timeout in seconds for Ollama assist requests (allows for cold start). |


---

## Prompt-Injection Robustness & Safety (AI Triage)

When `AI_TRIAGE_MODE="llm"`, tickets are sent to a local large language model for categorization and priority hint generation. Because user-submitted ticket text is inherently untrusted, the triage pipeline implements a **two-tier defense** against prompt-injection attacks (instruction overrides, role impersonation, simulated triage formatting, polite extraction, and executive priority inflation).

### Two-Tier Defense Architecture

1. **Tier 1: Deterministic Heuristic Injection Guard (`app/ai/injection_guard.py`)**
   - **Fast Pre-Screening**: Tickets are inspected before any prompt is assembled or sent to the LLM.
   - **Obfuscation Normalisation**: Normalises Unicode (NFKC), removes invisible / zero-width characters (`\u200b`, `\ufeff`), lowercases tokens, and collapses letter-spaced words (e.g. `u r g e n t` $\rightarrow$ `urgent`, `c-a-t-e-g-o-r-y` $\rightarrow$ `category`).
   - **Syntactically Anchored Rules**: Detects adversarial directives (`ignore previous instructions`, `system prompt reset`), role impersonation headers (`SYSTEM:`, `Agent triage note:`), format breaks (`--- Reference Ticket #1 ---`, raw JSON classification blocks), explicit classification directives, and executive escalation social engineering.
   - **Zero False Positives on Benign IT Queries**: Strict anchoring ensures innocent tickets using words like *urgent*, *ignore*, *system*, or *priority* (e.g. "urgent help with payroll", "please ignore the earlier alert", "Windows 11 system crash") are **never flagged** (0.0% false-positive rate across 190 clean benchmark tickets).
   - **Safe Similarity Fallback**: When an injection pattern is detected, the pipeline **bypasses the LLM entirely** and routes directly to similarity-weighted kNN fallback with `fallback_reason = "possible_prompt_injection"`.
   - **Privacy Integrity**: The guard returns only boolean flags and rule identifiers; it never includes or leaks raw ticket text in result objects.

2. **Tier 2: Prompt Boundary Isolation & Escaping (`app/ai/llm_triage.py` V2)**
   - **Boundary Delimiters**: Raw ticket text is enclosed in strict `<ticket_data>...</ticket_data>` boundary tags.
   - **Character Escaping**: All angle brackets within untrusted ticket text are neutralized (`<` $\rightarrow$ `&lt;`, `>` $\rightarrow$ `&gt;`, with `&` $\rightarrow$ `&amp;` escaped first), ensuring injected text cannot escape the boundary context.
   - **System Instruction Hardening**: Explicit system prompt instructions remind the model that everything inside `<ticket_data>` is untrusted user text to be classified, never system instructions or commands.

### User Interface Advisory
When a prompt-injection attempt is detected and routed to kNN similarity fallback, the UI displays an honest, non-punitive notice in the AI Triage Advisory box:
> *"Possible prompt injection detected. Showing the similarity-based suggestion instead."*

This ensures the user still receives an accurate, similarity-based suggestion based on historical tickets without giving an attacker access to LLM prompt execution.

### Empirical Robustness & Evaluation Splits

The defense was benchmarked across three separate evaluation datasets:
1. **Independent Held-Out Set (v2, $N = 30$)**: Authored completely independently outside this workflow and evaluated once. Heuristic guard detection was **36.7%** (11/30, missing 19 novel attack phrasings and lexical stuffing), but prompt boundary isolation kept overall attacked ASR to **6.7%** (2/30 [1.8%, 21.3%]), **comparable to kNN** at **13.3%** (4/30 [5.3%, 29.7%]) with overlapping intervals. Under keyword stuffing (`lexical_stuffing`), pure kNN suffered an 80.0% (4/5) attack success rate, while the full LLM defense resisted completely (0.0%, 0/5).
2. **In-Workflow Held-Out Set (v1, $N = 30$, Frozen by Process)**: Authored by the same agent in the same workflow and frozen before defense implementation (held out by process, not independent). Attacked ASR drops from **63.3%** to **13.3%** (4/30 [5.3%, 29.7%]), which is **comparable to kNN** at **20.0%** (6/30 [9.5%, 37.3%]) with overlapping confidence intervals.
3. **Development Set ($N = 40$, tuned on this set)**: Attacked Attack Success Rate (ASR) drops from **55.0%** to **2.5%** with full defense.
4. **False-Positive Rate on Clean Tickets**: Verified **0.0%** false-positive rate across 220 clean problem descriptions [0.0%, 1.7%].

### Security Limitations & Caveats
- **Small Sample Sizes**: Datasets of 30–40 tickets yield wide confidence intervals (±10–15 percentage points).
- **Heuristic Evasion**: Deterministic regexes can be evaded by paraphrasing, unfamiliar phrasing, leetspeak, or unsupported languages.
- **Model Scope**: Benchmarks reflect `llama3.1:8b` via Ollama; different models or parameter scales may exhibit different susceptibility.
- **Lexical Keyword Stuffing**: The guard does not address repeated keyword stuffing targeted at similarity search (in v2, lexical stuffing achieved 80% ASR against pure kNN).
- **Human-in-the-Loop Review**: Triage suggestions are strictly automated aids; service desk agents always verify and review tickets before taking operational action.

For detailed attack-type breakdowns, confusion tables, and empirical benchmark numbers, see [benchmarks/INJECTION.md](../benchmarks/INJECTION.md).
