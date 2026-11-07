# Benchmark Report: Keyword-Stuffing Mitigation for hashing-v2 kNN

## 1. Pre-Registration Confirmation

- **Git HEAD Commit**: `79211ed2514b5ab40e8328ce0f2c9320eaddc41a`
- **Pre-registration Protocol**: `benchmarks/STUFFING_PREREG.md`
  - **SHA-256 (LF)**: `db032ca18bafc8469ae12e0dc7fe2069e83e8003cb12b93501d9abe21355900c`
- **Tuning Dataset**: `data/injection/stuffing_dev.jsonl` (n=20)
  - **SHA-256 (LF)**: `e89d1ddd0b193251d594b2c51bb8973eeb4e71e689d2ed4c45b8194861ec5419`

## 2. Step 1: Eligibility (5-Fold Cross-Validation on Train Split, n=480)

A candidate is eligible if category accuracy and exact priority accuracy are each within 1.0 percentage point (pp) of the baseline under identical folds.

| Candidate | Stored Cap | Query Cap | Cat Acc (%) | Cat Delta (pp) | Prio Acc (%) | Prio Delta (pp) | Eligible? |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `baseline` | None | None | 60.00% | +0.00 | 53.96% | +0.00 | Baseline |
| `A1` | None | 1 | 58.75% | -1.25 | 52.29% | -1.67 | Ineligible |
| `A2` | None | 2 | 60.42% | +0.42 | 53.54% | -0.42 | **ELIGIBLE** |
| `A3` | None | 3 | 59.17% | -0.83 | 53.96% | +0.00 | **ELIGIBLE** |
| `B1` | 1 | 1 | 58.33% | -1.67 | 53.96% | +0.00 | Ineligible |
| `B2` | 2 | 2 | 60.83% | +0.83 | 52.29% | -1.67 | Ineligible |
| `B3` | 3 | 3 | 59.79% | -0.21 | 53.75% | -0.21 | **ELIGIBLE** |

## 3. Step 2: Selection on stuffing_dev (n=20)

Evaluated on `stuffing_dev.jsonl` (n=20) with full train pool (n=480). Tie-breaking rule: fewest successes, then prefer family A over B, then larger cap.

| Candidate | Attack Successes (n=20) | Attack Success Rate | Reduction vs Baseline | Status / Rank |
|:---|:---:|:---:|:---:|:---:|
| `baseline` | 5/20 | 25.0% | 0.0% | Baseline |
| `A2` | 5/20 | 25.0% | +0.0% | Evaluated |
| `A3` | 5/20 | 25.0% | +0.0% | Evaluated |
| `B3` | 5/20 | 25.0% | +0.0% | Evaluated |

## 4. Stop-Rule Evaluation

> [!IMPORTANT]
> **Study Stopped at Step 2 by Pre-Registered Rule**: `Uninformative set: baseline had 5 < 8 successes.`

- **Condition 1 (Baseline Informative Threshold)**: Baseline achieved 5/20 attack successes. Because this is strictly fewer than the pre-registered minimum of 8 successes, the dev set is uninformative for discriminating reductions, triggering an immediate stop.

Result: **Inconclusive: the pre-registered stuffing_dev set was uninformative (baseline 5/20 < 8)**.

## 5. Step 3: Evaluation of Winner vs Baseline

*Step 3 was not executed because the pre-registered stop rule was triggered at Step 2 (Uninformative set: baseline had 5 < 8 successes.). Pursuant to protocol, evaluation stopped to prevent uninformative testing.*

## 6. Scope of Mitigation: Addressed vs. Unaddressed Stuffing Styles

A feature-count cap (`cap: int`) in `HashingEmbedder` applies to the raw term frequencies before sublinear TF scaling (`1 + log(tf)`). Consequently, the cap operates differently across structural stuffing archetypes:

1. **Repeated Words / Repetitive Phrases**: Effective in theory. When an attacker repeats the same trigger word (e.g., `"urgent urgent urgent ..."` or `"network network wifi ..."`), the raw count is clamped to `cap`. This bounds the term's contribution to `1 + log(cap)`.
2. **Keyword Lists of Distinct Words**: When an attacker appends a trailer containing a wide vocabulary of domain words (e.g., 6 to 12 distinct keywords like `outlook mailbox email inbox delivery bounce attachment exchange`), each distinct keyword occurs usually once (`count = 1`). Because each distinct word appears once, a count cap has little or no effect on word features (char n-grams can still repeat).
3. **Interleaved Domain Vocabulary**: When domain keywords are distributed naturally through the ticket text with count 1, a count cap has little or no effect on word features.

### Empirical Breakdown on `stuffing_dev` (n=20)

| Candidate | Keyword List (n=12) | Repeated Words (n=4) | Interleaved (n=4) | Total (n=20) |
|:---|:---:|:---:|:---:|:---:|
| `baseline` | 2/12 (16.7%) | 2/4 (50.0%) | 1/4 (25.0%) | 5/20 (25.0%) |
| `A2` | 2/12 (16.7%) | 2/4 (50.0%) | 1/4 (25.0%) | 5/20 (25.0%) |
| `A3` | 2/12 (16.7%) | 2/4 (50.0%) | 1/4 (25.0%) | 5/20 (25.0%) |
| `B3` | 2/12 (16.7%) | 2/4 (50.0%) | 1/4 (25.0%) | 5/20 (25.0%) |

> [!NOTE]
> No benefit was observed for A2, A3, B3 on this set; for keyword-list and interleaved tickets each distinct word usually appears once, so a count cap has little or no effect on word features (char n-grams can still repeat); with n=4 repeated-word tickets no conclusion is possible.

## 7. Limitations

- **Weak dev set**: stuffing_dev baseline success rate is 5/20 (25%) while hashing-v2 succeeded on 7 of 8 held-out lexical_stuffing tickets (held-out v1+v2), so the authored dev set was much weaker than the real attacks and could not discriminate.
- **Step 3 not run**: Pursuant to the pre-registered stop rule, Step 3 was not run.
- **Unplanned exploratory run on held-out tickets**: An unplanned exploratory run, performed AFTER Step 2 had already stopped the study and outside the pre-registered protocol, evaluated the baseline and A2, A3, B3 on the 8 held-out lexical_stuffing tickets (baseline: 7/8, A2: 6/8, A3: 6/8, B3: 6/8, read from `exploratory_heldout_stuffing.json`). It violated the pre-registration rule against looking at held-out results for candidates; it was not used for any decision; n=8, so no conclusion is drawn; consequently these 8 held-out tickets must not be treated as clean held-out data for any future stuffing mitigation, which needs fresh held-out tickets.
- **Test split not touched**: The test split (`data/servicedesk600/test.jsonl`) was not touched by any candidate run in this study; because Step 2 stopped, `run_step3_eval` was never called, keeping the test split unexamined.
- **Experimenter bias risk**: The dev set was authored by the same agent that implemented the candidates.
