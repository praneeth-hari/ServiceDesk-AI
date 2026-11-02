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

### Final Evaluation on Test Split (N=24)

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
