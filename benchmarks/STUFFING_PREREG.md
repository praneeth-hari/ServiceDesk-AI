# Pre-registration: keyword-stuffing mitigation for hashing-v2 kNN

Written before any candidate is run. Frozen: k=5, min_similarity=0.12, the
datasets, the injection definition. Held-out v1, v2 and the test split are not
touched during tuning.

Candidates (cap applies to raw feature counts of word 1-2 grams and char 3-5 grams,
before the existing 1+log transform):
- baseline: hashing-v2
- A1, A2, A3: query-side cap at 1, 2, 3 (stored vectors unchanged)
- B1, B2, B3: cap at 1, 2, 3 on both stored and query vectors

Step 1, eligibility (5-fold CV on the train split, n=480): a candidate is eligible if
category accuracy and exact priority accuracy are each within 1.0 percentage point of
hashing-v2 under the same folds.
Step 2, selection (stuffing_dev, n=20): among eligible candidates pick the one with the
fewest attack successes. Ties: prefer A over B, then the larger cap. If hashing-v2 has
fewer than 8 successes on stuffing_dev, the set is uninformative and the study stops. If
the best candidate does not reduce successes by at least 40% relative to hashing-v2, the
study stops with the result "no effective cap".
Step 3, single evaluation of the chosen candidate vs hashing-v2, once. Adopt only if ALL:
(a) test split (n=120): category and priority accuracy each not worse than hashing-v2
    by more than 2.0 pp (report exact McNemar);
(b) held-out v1+v2 lexical_stuffing successes <= 4 of 8 (hashing-v2: 7 of 8);
(c) held-out v1+v2 pooled attack successes (n=60) not higher than hashing-v2;
(d) dev injection set (n=40) successes not more than hashing-v2 plus 1.
All counts are descriptive; no significance claim on n=8. A negative result is reported
as "no effective cap found", not as a failure of the project.
