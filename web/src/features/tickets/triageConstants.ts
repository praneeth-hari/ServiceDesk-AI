/**
 * Benchmark evaluation metrics for AI triage.
 * Source reference: docs/AI_TRIAGE.md (evaluated on held-out test split of 24 tickets from synthetic 120-ticket dataset).
 */

export const TRIAGE_BENCHMARKS = {
  categoryAccuracyPercent: 58,
  categoryAccuracyExact: '58.33%',
  categoryRandomChance: '16.67%',
  categoryMajorityBaseline: '16.67%',
  priorityAccuracyExact: '37.50%',
  priorityMajorityBaseline: '38.33%',
  testSplitSize: 24,
  totalDatasetSize: 120,
  minTextLength: 15,
  debounceMs: 600,
} as const;

export const TRIAGE_HONESTY_SUMMARY =
  `Measured: ${TRIAGE_BENCHMARKS.categoryAccuracyPercent}% category accuracy vs 17% by chance.`;

export const TRIAGE_EXPLANATION =
  `Category accuracy is ${TRIAGE_BENCHMARKS.categoryAccuracyExact} (vs ${TRIAGE_BENCHMARKS.categoryRandomChance} random chance). Priority hint is ${TRIAGE_BENCHMARKS.priorityAccuracyExact} (vs ${TRIAGE_BENCHMARKS.priorityMajorityBaseline} majority class baseline). Evaluated on ${TRIAGE_BENCHMARKS.testSplitSize} held-out tickets from a synthetic ${TRIAGE_BENCHMARKS.totalDatasetSize}-ticket dataset (docs/AI_TRIAGE.md). The method compares text with past tickets (lexical feature hashing, not semantic understanding).`;

