# ServiceDesk500 Validation Report

**Execution command:** `python -m app.scripts.build_dataset`

## 1. Batch Loading Summary

| Batch File | Valid Tickets Loaded | Status |
| :--- | :--- | :--- |
| `batch_01.jsonl` | 50 | Valid |
| `batch_02.jsonl` | 50 | Valid |
| `batch_03.jsonl` | 50 | Valid |
| `batch_04.jsonl` | 50 | Valid |
| `batch_05.jsonl` | 50 | Valid |
| `batch_06.jsonl` | 50 | Valid |
| `batch_07.jsonl` | 50 | Valid |
| `batch_08.jsonl` | 50 | Valid |
| `batch_09.jsonl` | 50 | Valid |
| `batch_10.jsonl` | 50 | Valid |
| `batch_11.jsonl` | 50 | Valid |
| `batch_12.jsonl` | 50 | Valid |

- **Total valid tickets loaded:** 600
- **Total rejected rows:** 0

## 2. Rejected Rows

No rows were rejected. All batch files passed schema and domain validation.

## 3. Near-Duplicate Pairs (Cosine Similarity > 0.85)

Evaluated pairwise similarity using `HashingEmbedder` (`hashing-v2`, 4096 dimensions).
Pairs found above threshold (0.85): **0**

No near-duplicate pairs above 0.85 cosine similarity were found in the dataset.

## 4. Human Review Corrections Applied

| Ticket ID | Field | Old Value | Corrected Value |
| :--- | :--- | :--- | :--- |
| `EML-062` | `priority` | `high` | `urgent` |
| `SW-045` | `priority` | `urgent` | `high` |
| `EML-006` | `priority` | `medium` | `low` |
| `HW-090` | `priority` | `medium` | `low` |
| `OTH-034` | `priority` | `medium` | `low` |
| `OTH-078` | `priority` | `medium` | `low` |
| `OTH-098` | `priority` | `medium` | `low` |
| `OTH-006` | `priority` | `medium` | `low` |
| `OTH-011` | `priority` | `medium` | `low` |
| `OTH-013` | `priority` | `medium` | `low` |
| `OTH-019` | `priority` | `medium` | `low` |
| `OTH-033` | `priority` | `medium` | `low` |
| `OTH-039` | `priority` | `medium` | `low` |
| `OTH-049` | `priority` | `medium` | `low` |
| `OTH-065` | `priority` | `medium` | `low` |
| `OTH-069` | `priority` | `medium` | `low` |
| `OTH-074` | `priority` | `medium` | `low` |
| `OTH-083` | `priority` | `medium` | `low` |
| `OTH-093` | `priority` | `medium` | `low` |
| `OTH-095` | `priority` | `medium` | `low` |
| `OTH-022` | `priority` | `medium` | `low` |
| `OTH-028` | `priority` | `medium` | `low` |
| `OTH-044` | `priority` | `medium` | `low` |
| `OTH-053` | `priority` | `medium` | `low` |
| `OTH-060` | `priority` | `medium` | `low` |
| `OTH-064` | `priority` | `medium` | `low` |
| `OTH-100` | `priority` | `medium` | `low` |

## 5. Train / Test Split Tables (80% Train / 20% Test, Seed 42)

### Category Distribution

| Category | Total | Train | Test | Train % | Test % |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `access` | 100 | 80 | 20 | 80.0% | 20.0% |
| `email` | 100 | 80 | 20 | 80.0% | 20.0% |
| `hardware` | 100 | 80 | 20 | 80.0% | 20.0% |
| `network` | 100 | 80 | 20 | 80.0% | 20.0% |
| `other` | 100 | 80 | 20 | 80.0% | 20.0% |
| `software` | 100 | 80 | 20 | 80.0% | 20.0% |
| **Total** | **600** | **480** | **120** | **80.0%** | **20.0%** |

### Priority Distribution

| Priority | Total | Train | Test | Train % | Test % |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `low` | 145 | 114 | 31 | 78.6% | 21.4% |
| `medium` | 215 | 175 | 40 | 81.4% | 18.6% |
| `high` | 144 | 118 | 26 | 81.9% | 18.1% |
| `urgent` | 96 | 73 | 23 | 76.0% | 24.0% |
| **Total** | **600** | **480** | **120** | **80.0%** | **20.0%** |

### Difficulty Distribution

| Difficulty | Total | Train | Test | Train % | Test % |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `easy` | 444 | 354 | 90 | 79.7% | 20.3% |
| `hard` | 156 | 126 | 30 | 80.8% | 19.2% |
| **Total** | **600** | **480** | **120** | **80.0%** | **20.0%** |

