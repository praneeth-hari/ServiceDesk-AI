# Pre-registration: nomic-retrieved examples for LLM triage

Written before any run. Question: does retrieving the in-context examples with
nomic-embed-text (instead of hashing-v2) improve LLM triage?

Setup (frozen): same LLM (llama3.1:8b), same hardened prompt v2, same number of
examples, same min_similarity, same train pool (480) and test split (120), same
generation settings. Only the retrieval space for the examples differs.
Methods: existing hashing-retrieved llm-rag (baseline) vs new llm-rag-nomic.

Primary endpoints (test split, n=120, paired): category accuracy and exact
priority accuracy. Test: exact two-sided McNemar on discordant pairs, alpha = 0.025
per endpoint (Bonferroni for two).

Decision rule. Adopt nomic examples in the app only if ALL hold:
1. At least one primary endpoint is better for nomic by >= 5.0 percentage points
   with p < 0.025.
2. Neither primary endpoint is worse by more than 2.0 percentage points.
3. Injection, held-out v1 + v2 pooled (60 tickets, LLM mode with full defenses):
   nomic attack successes <= hashing attack successes + 1.
4. Median warm latency of the full request is at most 150 ms slower than the
   baseline.
If any condition fails, examples stay on hashing-v2. A null or negative result is
reported as "no evidence of benefit", not as proof of no difference (n=120 has low
power for small effects).

Secondary (descriptive only, not used for the decision): within-one priority,
macro-F1, hard-ticket accuracy, JSON validity rate, fallback rate, latency p50/p95.

No tuning on the test split, no re-runs with changed settings. Any later variant is
exploratory and must be labelled as such.

