# Ticket Triage Benchmark Evaluation Report

Evaluation of automated category and priority triage methods on the **ServiceDesk600** benchmark dataset (`data/servicedesk600`, split `test.jsonl`, N=120).

### Dataset Provenance & Cryptographic Hashes
- **`data/servicedesk600/train.jsonl` SHA-256**: `657ebf3745306c92e8b4dc077e4eb5382ebee442645656d333d6b579d9423482`
- **`data/servicedesk600/test.jsonl` SHA-256**: `9b3f5b7f779e54424be8271e2ac53624cc7f0098670dcc84d1869b84e72769ac`
- **Curation Verification**: Confirmed benchmark dataset includes all 27 human review corrections from `review_corrections.csv`.

## 1. Headline Benchmark Results

The headline results below quote the canonical benchmark figures from the original ServiceDesk-600 evaluation (Prompt V1 across all methods, N=120 test tickets):

| Method | Category Accuracy [95% CI] | Cat Macro-F1 | Priority Accuracy [95% CI] | Priority Within-One | Hard-Ticket Cat Acc | Mean Latency / Ticket | Total Run Time | Invalid Rate |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| *Baseline: Majority Class* | 16.7% [11.1%, 24.3%] | 0.0476 | 33.3% [25.5%, 42.2%] | 80.8% | 16.7% | <0.1 ms | <0.1s | 0.0% |
| *Baseline: Random Guess (seed=42)* | 10.8% [6.4%, 17.7%] (expected: 16.7% [1/6]) | 0.1082 | 30.0% [22.5%, 38.7%] (expected: 25.0% [1/4]) | 65.0% | 10.0% | <0.1 ms | <0.1s | 0.0% |
| **`llm-rag`** | **87.5%** [80.4%, 92.3%] | 0.8711 | 69.2% [60.4%, 76.7%] | 98.3% | 76.7% | 2376.7 ms | 267.1s | 0.0% |
| **`llm-rag-hashing`** | **85.8%** [78.5%, 91.0%] | 0.8584 | 64.2% [55.3%, 72.2%] | 96.7% | 70.0% | 2736.3 ms | 328.7s | 0.0% |
| **`llm-rag-qwen3b`** | **83.3%** [75.6%, 88.9%] | 0.8232 | 60.0% [51.1%, 68.3%] | 95.8% | 70.0% | 441.8 ms | 70.2s | 0.0% |
| **`llm-zero-shot-qwen3b`** | **80.8%** [72.9%, 86.9%] | 0.8046 | 55.8% [46.9%, 64.4%] | 95.8% | 73.3% | 360.4 ms | 43.3s | 0.0% |
| **`llm-zero-shot`** | **79.2%** [71.0%, 85.5%] | 0.7848 | 68.3% [59.6%, 76.0%] | 99.2% | 70.0% | 2111.3 ms | 222.4s | 0.0% |
| **`minilm-knn`** | **76.7%** [68.3%, 83.3%] | 0.7571 | 47.5% [38.8%, 56.4%] | 85.0% | 70.0% | 0.9 ms | 14.4s | 0.0% |
| **`bge-small-knn`** | **69.2%** [60.4%, 76.7%] | 0.6673 | 45.0% [36.4%, 53.9%] | 88.3% | 56.7% | 1.0 ms | 9.3s | 0.0% |
| **`hashing-knn`** | **62.5%** [53.6%, 70.7%] | 0.6100 | 44.2% [35.6%, 53.1%] | 81.7% | 56.7% | 1.1 ms | 0.3s | 0.0% |

> **Baseline Clarification (Priority Accuracy)**: Training set majority priority is `medium` (175/480 tickets = 36.5%). In `test.jsonl`, there are exactly 40 `medium` tickets out of 120 (with 31 `low`, 26 `high`, 23 `urgent`). Predicting `medium` for all test tickets yields an exact priority accuracy of **33.3%** (40/120 = 0.3333).

### Prompt Hardening Evaluation (Prompt V1 vs Hardened Prompt V2)

To defend against prompt injection attacks, LLM triage prompts were upgraded from V1 to hardened V2 (enclosing user input in strict `<ticket_data>` boundaries, HTML entity escaping `<` and `>`, and adding safety instructions).

Below is the verified side-by-side comparison evaluated on the identical 120 test tickets of ServiceDesk-600 (drawn directly from `benchmarks/results/` and `benchmarks/results_v2/`):

| Method | Prompt Version | Category Acc (exact) [95% CI] | Priority Acc (exact) [95% CI] | Priority Within-One [95% CI] | Combined Acc (both exact) [95% CI] | Category McNemar p-value | Priority McNemar p-value | Combined McNemar p-value |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: | :---: | :---: |
| `llm-zero-shot` | V1 (unhardened) | 79.2% (95/120) [71.0%, 85.5%] | 68.3% (82/120) [59.6%, 76.0%] | 99.2% (119/120) [95.4%, 99.9%] | 50.8% (61/120) [42.0%, 59.6%] | — | — | — |
| `llm-zero-shot` | V2 (hardened) | 85.0% (102/120) [77.5%, 90.3%] | 60.0% (72/120) [51.1%, 68.3%] | 96.7% (116/120) [91.7%, 98.7%] | 49.2% (59/120) [40.4%, 58.0%] | p = 0.0923 (b=10, c=3) | p = 0.0129 (b=2, c=12) | p = 0.7905 (b=6, c=8) |
| `llm-rag` | V1 (unhardened) | 87.5% (105/120) [80.4%, 92.3%] | 69.2% (83/120) [60.4%, 76.7%] | 98.3% (118/120) [94.1%, 99.5%] | 58.3% (70/120) [49.4%, 66.8%] | — | — | — |
| `llm-rag` | V2 (hardened) | 86.7% (104/120) [79.4%, 91.6%] | 68.3% (82/120) [59.6%, 76.0%] | 98.3% (118/120) [94.1%, 99.5%] | 59.2% (71/120) [50.2%, 67.6%] | p = 1.0000 (b=3, c=4) | p = 1.0000 (b=7, c=8) | p = 1.0000 (b=8, c=7) |
| `llm-rag-hashing` | V1 (unhardened) | 85.8% (103/120) [78.5%, 91.0%] | 64.2% (77/120) [55.3%, 72.2%] | 96.7% (116/120) [91.7%, 98.7%] | 53.3% (64/120) [44.4%, 62.0%] | — | — | — |
| `llm-rag-hashing` | V2 (hardened) | 85.0% (102/120) [77.5%, 90.3%] | 62.5% (75/120) [53.6%, 70.7%] | 97.5% (117/120) [92.9%, 99.1%] | 50.0% (60/120) [41.2%, 58.8%] | p = 1.0000 (b=1, c=2) | p = 0.7744 (b=5, c=7) | p = 0.4239 (b=5, c=9) |

> **Column Definitions & Underlying Keys**:
> - **Category Acc (exact)**: Exact match accuracy on ground-truth category (`category_metrics.accuracy`).
> - **Priority Acc (exact)**: Exact match accuracy on ground-truth priority (`priority_metrics.accuracy`).
> - **Priority Within-One**: Proportion of predictions within $\pm 1$ level of ground-truth priority (`priority_metrics.within_one_accuracy`).
> - **Combined Acc (both exact)**: Proportion of tickets where both category and priority exactly matched ground truth (`predictions` item matching both true fields).
>
> **Statistical Significance Summary (McNemar Exact Tests)**:
> - **Category Accuracy**: No statistically significant difference between V1 and V2 for any method (`llm-zero-shot` $p = 0.0923$, `llm-rag` $p = 1.0000$, `llm-rag-hashing` $p = 1.0000$). The zero-shot category difference is **not statistically significant**.
> - **Priority Accuracy**: For `llm-zero-shot`, exact priority match showed a statistically significant drop ($p = 0.0129$, with 12 tickets correct in V1 but missed in V2 vs. 2 correct in V2 but missed in V1). For `llm-rag` ($p = 1.0000$) and `llm-rag-hashing` ($p = 0.7744$), priority accuracy showed no significant difference.
> - **Combined Accuracy**: No statistically significant difference across any method (`llm-zero-shot` $p = 0.7905$, `llm-rag` $p = 1.0000$, `llm-rag-hashing` $p = 0.4239$).

---

## 2. Best Method Analysis (`llm-rag`)

**Best Performing Model**: `llm-rag` achieved **86.7%** category accuracy and **0.8626** macro-F1.

### Category Confusion Pairs (11 distinct pairs)

| True Category | Predicted As | Total Count | Hard Tickets |
| :--- | :--- | :---: | :---: |
| `software` | `access` | 3 | 2 |
| `other` | `network` | 3 | 0 |
| `other` | `hardware` | 2 | 0 |
| `access` | `hardware` | 1 | 1 |
| `access` | `email` | 1 | 1 |
| `hardware` | `other` | 1 | 1 |
| `network` | `other` | 1 | 1 |
| `other` | `email` | 1 | 1 |
| `software` | `hardware` | 1 | 1 |
| `other` | `access` | 1 | 0 |
| `software` | `email` | 1 | 0 |

### Priority Errors & 4x4 Confusion Matrix

| True Priority \ Predicted | `low` | `medium` | `high` | `urgent` |
| :--- | :---: | :---: | :---: | :---: |
| **`low`** | 21 | 9 | 0 | 1 |
| **`medium`** | 1 | 32 | 7 | 0 |
| **`high`** | 0 | 3 | 21 | 2 |
| **`urgent`** | 0 | 1 | 14 | 8 |

> **Error Direction**: Across 38 total priority errors (31.7% of the test set), misclassifications were evenly balanced between 19 over-predicted tickets (15.8%) and 19 under-predicted tickets (15.8%).

### Category Failure Examples

Showing 8 category misclassifications for `llm-rag`, spread across all categories with errors (note: `email` achieved 100% accuracy with 0 errors):

#### Example 1: Ticket `NET-060` (HARD)
- **Ticket Text**:
  > beeping noise in corridor cupboard
  > theres a loud beeping coming from the cupboard by the lifts on level 2, the one with all the blue cables. been going since about 7 this morning. everythings working as far as i can tell but i dont know if its a warning about something
- **True Category**: `network` | **Predicted Category**: `other`
- **Label Note**: *"An alarm from the comms cupboard most likely comes from network kit or its UPS, so it is routed to network; the user can't tell what it is, it could be confused with hardware or other, and priority is debatable since nothing has failed yet."*

#### Example 2: Ticket `HW-099` (HARD)
- **Ticket Text**:
  > old work phone - personal photos on it
  > I got a new work phone a month ago and the old one is in my drawer. It has some personal photos on it I'd like to keep before I hand it back. Can someone help me get them off and then take the old phone?
- **True Category**: `hardware` | **Predicted Category**: `other`
- **Label Note**: *"Returning a device and transferring its data is hardware handling and low; the personal-photos element could make it look like an other (general request) ticket."*

#### Example 3: Ticket `SW-005` (HARD)
- **Ticket Text**:
  > all my files have changed to .locked
  > All the files in my Documents folder and on the team share now end in .locked and won't open. There's a text file on my desktop called READ_ME_NOW saying to pay to get them back. My PC is still on. Colleagues on the same share say their files are changing too.
- **True Category**: `software` | **Predicted Category**: `access`
- **Label Note**: *"Ransomware actively encrypting files is malicious software on the endpoint, so it is labelled software and urgent as a security incident causing data loss; it could also be routed as other or as a dedicated security incident."*

#### Example 4: Ticket `ACC-044` (HARD)
- **Ticket Text**:
  > 40 graduates started today - no accounts
  > Our graduate intake of 40 started at 9am today in the Chennai training centre. None of them have accounts, so they can't log in to the training laptops. The request went in three weeks ago. The trainers are presenting from the projector for now.
- **True Category**: `access` | **Predicted Category**: `hardware`
- **Label Note**: *"Missing new-joiner accounts are access; priority is debatable because no business system is down and training continues on the projector (high), but 40 people blocked justifies urgent."*

#### Example 5: Ticket `OTH-004` (EASY)
- **Ticket Text**:
  > boardroom screen not showing anything - client at 11
  > The big screen in the boardroom just shows 'no source' whatever we plug in, and the wireless share button does nothing. A client arrives at 11 for a contract presentation.
- **True Category**: `other` | **Predicted Category**: `network`
- **Label Note**: *"A meeting-room display fault is AV, so it is other, and it is high because a client meeting is at risk."*

#### Example 6: Ticket `SW-017` (EASY)
- **Ticket Text**:
  > PayRun says licence expired - payroll due today
  > PayRun opened this morning with 'Your licence has expired. Contact your administrator.' and won't go past the login screen for anyone in the payroll team. Monthly payroll for 1,800 staff has to reach the bank by 4pm today.
- **True Category**: `software` | **Predicted Category**: `access`
- **Label Note**: *"An expired application licence is software, and it is urgent because a business-critical payroll run is blocked today."*

#### Example 7: Ticket `ACC-077` (HARD)
- **Ticket Text**:
  > entered my password on a fake page?
  > I clicked a link in an email about a shared invoice and it took me to a login page that looked like ours. I entered my username and password, then it went blank. Now I've noticed the address was odd. I'm in accounts payable and I can change supplier bank details.
- **True Category**: `access` | **Predicted Category**: `email`
- **Label Note**: *"Compromised credentials need an immediate reset and session revoke, so it is access and urgent because of privileged finance access; it could be routed to email as a phishing report."*

#### Example 8: Ticket `OTH-021` (HARD)
- **Ticket Text**:
  > room panel shows a meeting that was cancelled
  > The booking panel outside room 4A shows a recurring meeting every morning that was cancelled weeks ago, so people think the room is taken and leave. The room is actually free.
- **True Category**: `other` | **Predicted Category**: `email`
- **Label Note**: *"The room panel is meeting-room AV, so it is labelled other and medium, but the likely cause is the room's calendar resource, so it could be routed to email."*

---

## 3. Statistical Significance Testing (McNemar Exact Test)

Paired two-sided McNemar exact test evaluating whether `llm-rag` (`llama3.1:8b`) category classification accuracy significantly outperforms retrieval baselines across the 120 test tickets:

| Comparison | Discordant Pairs (A correct, B wrong) | Discordant Pairs (A wrong, B correct) | Total Discordant (n) | Exact Two-Sided p-value | Statistically Significant (α=0.05)? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `llm-rag` vs `hashing-knn` | 34 | 4 | 38 | **0.000001** | **Yes (p < 0.05)** |
| `llm-rag` vs `minilm-knn` | 18 | 5 | 23 | **0.010622** | **Yes (p < 0.05)** |
| `llm-rag-hashing` vs `hashing-knn` | 32 | 4 | 36 | **0.000002** | **Yes (p < 0.05)** |
| `llm-rag` vs `llm-rag-hashing` | 7 | 5 | 12 | **0.774414** | **No** |

- **`llm-rag` vs `hashing-knn`**: $p = 6.04 \times 10^{-7}$ ($b=34$ where `llm-rag` is correct and `hashing-knn` is wrong, $c=4$ where `hashing-knn` is correct and `llm-rag` is wrong), showing decisive statistical superiority ($p < 0.001$).
- **`llm-rag` vs `minilm-knn`**: $p = 0.010622$ ($b=18$ where `llm-rag` is correct and `minilm-knn` is wrong, $c=5$ where `minilm-knn` is correct and `llm-rag` is wrong), confirming that retrieved in-context examples provide a statistically significant improvement over dense embedding kNN alone at $\alpha = 0.05$.
- **`llm-rag-hashing` vs `hashing-knn`**: $p = 2.12 \times 10^{-6}$ ($b=32$ where `llm-rag-hashing` is correct and `hashing-knn` is wrong, $c=4$ where `hashing-knn` is correct and `llm-rag-hashing` is wrong), confirming that the app's shipped retrieval with Llama 3.1 significantly outperforms kNN alone ($p < 0.001$).
- **`llm-rag` vs `llm-rag-hashing`**: $p = 0.774414$ ($b=7$ where `llm-rag` is correct and `llm-rag-hashing` is wrong, $c=5$ where `llm-rag-hashing` is correct and `llm-rag` is wrong): no difference was detected (12 discordant pairs; the test cannot show equivalence).

---

## 4. Reproduction Commands

All benchmarks are fully deterministic and reproducible via the benchmark CLI script:

```bash
# 1. Install optional benchmark dependencies (sentence-transformers)
pip install -r requirements-bench.txt

# 2. Run kNN and embedding baselines
python -m app.scripts.benchmark_triage --methods hashing-knn,minilm-knn,bge-small-knn

# 3. Run LLM zero-shot and RAG with default Llama-3.1 (8B)
python -m app.scripts.benchmark_triage --methods llm-zero-shot,llm-rag --model llama3.1:8b

# 4. Run LLM zero-shot and RAG with Qwen-2.5 (3B)
python -m app.scripts.benchmark_triage --methods llm-zero-shot,llm-rag --model qwen2.5:3b
```

---

## 5. Honest Caveats & Limitations

1. **Synthetic Data Origin**: ServiceDesk600 was generated synthetically via Claude Opus 5.5. While engineered for realistic noise, typos, and urgency distributions, synthetic tickets may exhibit vocabulary patterns that models navigate differently than real-world corporate support queues.
2. **Sample Size & Confidence Intervals**: The held-out test split comprises 120 tickets (20 per category, 30 hard edge cases). With N=120, binomial 95% Wilson intervals span approximately ±6-8 percentage points; overlapping intervals should be interpreted with statistical caution.
3. **In-Prompt Definitions**: LLM prompts explicitly include canonical category and priority definitions, providing strong structured semantic guidance compared to purely inductive few-shot kNN.
4. **Single-Run Determinism**: All LLM queries were executed at `temperature=0` with `seed=42`. While locally deterministic, small differences may occur across hardware architectures or quantization variants.
