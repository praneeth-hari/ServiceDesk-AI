# Ticket Triage Benchmark Evaluation Report

Evaluation of automated category and priority triage methods on the **ServiceDesk600** benchmark dataset (`data/servicedesk600`, split `test.jsonl`, N=120).

### Dataset Provenance & Cryptographic Hashes
- **`data/servicedesk600/train.jsonl` SHA-256**: `657ebf3745306c92e8b4dc077e4eb5382ebee442645656d333d6b579d9423482`
- **`data/servicedesk600/test.jsonl` SHA-256**: `9b3f5b7f779e54424be8271e2ac53624cc7f0098670dcc84d1869b84e72769ac`
- **Curation Verification**: Confirmed benchmark dataset includes all 27 human review corrections from `review_corrections.csv`.

## 1. Headline Benchmark Results

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

---

## 2. Best Method Analysis (`llm-rag`)

**Best Performing Model**: `llm-rag` achieved **87.5%** category accuracy and **0.8711** macro-F1.

### Category Confusion Pairs (9 distinct pairs)

| True Category | Predicted As | Total Count | Hard Tickets |
| :--- | :--- | :---: | :---: |
| `software` | `hardware` | 3 | 2 |
| `other` | `network` | 3 | 0 |
| `software` | `access` | 2 | 2 |
| `other` | `hardware` | 2 | 0 |
| `access` | `email` | 1 | 1 |
| `hardware` | `other` | 1 | 1 |
| `network` | `other` | 1 | 1 |
| `other` | `access` | 1 | 0 |
| `software` | `email` | 1 | 0 |

### Priority Errors & 4x4 Confusion Matrix

| True Priority \ Predicted | `low` | `medium` | `high` | `urgent` |
| :--- | :---: | :---: | :---: | :---: |
| **`low`** | 21 | 8 | 1 | 1 |
| **`medium`** | 2 | 29 | 9 | 0 |
| **`high`** | 0 | 2 | 23 | 1 |
| **`urgent`** | 0 | 0 | 13 | 10 |

> **Error Direction**: Across 37 total priority errors (30.8% of the test set), misclassifications lean towards over-prediction of urgency with 20 tickets triaged at higher priority than ground truth (16.7%) versus 17 under-predicted tickets (14.2%), most notably 8 low-priority tickets escalated to medium and 9 medium-priority tickets escalated to high.

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

#### Example 4: Ticket `ACC-077` (HARD)
- **Ticket Text**:
  > entered my password on a fake page?
  > I clicked a link in an email about a shared invoice and it took me to a login page that looked like ours. I entered my username and password, then it went blank. Now I've noticed the address was odd. I'm in accounts payable and I can change supplier bank details.
- **True Category**: `access` | **Predicted Category**: `email`
- **Label Note**: *"Compromised credentials need an immediate reset and session revoke, so it is access and urgent because of privileged finance access; it could be routed to email as a phishing report."*

#### Example 5: Ticket `OTH-004` (EASY)
- **Ticket Text**:
  > boardroom screen not showing anything - client at 11
  > The big screen in the boardroom just shows 'no source' whatever we plug in, and the wireless share button does nothing. A client arrives at 11 for a contract presentation.
- **True Category**: `other` | **Predicted Category**: `network`
- **Label Note**: *"A meeting-room display fault is AV, so it is other, and it is high because a client meeting is at risk."*

#### Example 6: Ticket `SW-011` (HARD)
- **Ticket Text**:
  > computer acting up
  > computer acting up again since this morning. stuff not working properly
- **True Category**: `software` | **Predicted Category**: `hardware`
- **Label Note**: *"The ticket is vague with no app, symptom or device detail, so it is labelled software as the most common cause of general misbehaviour, with medium as a placeholder; it could equally be hardware or other."*

#### Example 7: Ticket `OTH-024` (EASY)
- **Ticket Text**:
  > video conference camera dead in boardroom 2
  > The camera in boardroom 2 shows a black image in every meeting. The board's call with the overseas investors is at 3pm in that room and they want video.
- **True Category**: `other` | **Predicted Category**: `hardware`
- **Label Note**: *"Meeting-room video equipment is AV, so it is other, and it is high because a high-stakes meeting is today."*

#### Example 8: Ticket `SW-023` (EASY)
- **Ticket Text**:
  > everything tiny on new screen
  > Since I got my new 4K monitor, text in most apps is tiny, and some older apps look blurry when I make them bigger. I've been zooming in on each window.
- **True Category**: `software` | **Predicted Category**: `hardware`
- **Label Note**: *"Display scaling is an OS setting, so it is software, and it is medium because zooming is a workaround."*

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
