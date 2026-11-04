/**
 * Benchmark evaluation metrics for AI triage.
 * Source reference: benchmarks/RESULTS.md (evaluated on held-out test split of 120 tickets from synthetic 600-ticket ServiceDesk-600 dataset).
 */

export const TRIAGE_BENCHMARKS = {
  categoryAccuracyPercent: 62.5,
  categoryAccuracyExact: '62.5%',
  categoryMajorityBaseline: '16.7%',
  priorityAccuracyExact: '44.2%',
  priorityMajorityBaseline: '33.3%',
  testSplitSize: 120,
  totalDatasetSize: 600,
  minTextLength: 15,
  debounceMs: 600,
} as const;

export const TRIAGE_HONESTY_SUMMARY =
  'Measured: 62.5% category accuracy vs 16.7% majority-class baseline (measured on the ServiceDesk-600 test split).';

export const TRIAGE_EXPLANATION =
  'Category accuracy is 62.5% (vs 16.7% majority-class baseline). Priority hint is 44.2% (vs 33.3% majority-class baseline). Evaluated on 120 held-out tickets from the synthetic 600-ticket ServiceDesk-600 dataset (benchmarks/RESULTS.md). The baseline method compares text with past tickets using lexical feature hashing.';
