# ServiceDesk600 Dataset Datasheet

## 1. Dataset Overview

**ServiceDesk600** is a benchmark dataset of 600 realistic IT service desk support tickets designed for evaluating and benchmarking automated IT ticket triage, categorization, priority suggestion, and duplicate detection systems.

The dataset was synthetically generated using **a large language model** in 12 structured batches of 50 tickets each, spanning realistic workplace IT problem domains, varied writing styles (e.g., panicked, terse, conversational, executive, non-native English, technical), and realistic severity levels. Approximately 26% of tickets are designated as "hard" edge cases featuring multiple potential categories, conflicting priority cues, or subtle technical symptoms. A ~10% stratified random sample (60 tickets) was designated for human review and validation.

---

## 2. Dataset Schema

Each ticket in `servicedesk600.jsonl`, `train.jsonl`, and `test.jsonl` is serialized as a JSON object with the following fields:

| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | `string` | Unique ticket identifier (e.g., `NET-001`, `HW-042`, `SW-099`). |
| `title` | `string` | Subject or brief summary of the ticket (at least 3 characters). |
| `description` | `string` | Detailed description of the problem or service request (at least 10 characters). |
| `category` | `string` | One of 6 mutually exclusive ticket categories: `network`, `hardware`, `software`, `access`, `email`, `other`. |
| `priority` | `string` | One of 4 operational priority tiers: `low`, `medium`, `high`, `urgent`. |
| `difficulty` | `string` | Triage classification difficulty: `easy` (straightforward) or `hard` (ambiguous/composite). |
| `label_note` | `string` | Ground truth explanation explaining why the category and priority were assigned. |
| `group` | `string` | Group identifier for near-duplicates; guarantees that identical or near-duplicate tickets remain strictly together in the same split. |

When loaded programmatically via `app.ai.dataset.load_split()`, each record returns a `TicketExample` object containing:
- `id`: Ticket ID
- `text`: Concatenated title and description (`f"{title}\n{description}"`), strictly omitting `label_note` and ground-truth labels.
- `category`: Category label
- `priority`: Priority label
- `difficulty`: Difficulty tier
- `group`: Group identifier

---

## 3. Category & Priority Definitions

### Categories
- **`network`**: Wi-Fi connectivity, wired Ethernet, VPN access/routing, DNS resolution, corporate switches/routers, firewall blocks, remote connectivity, and ISP/site-wide connectivity issues.
- **`hardware`**: Physical computing devices, laptop/desktop hardware failures, external monitors/peripherals, docks/cables, physical servers/disks, and procurement requests for new devices.
- **`software`**: Application and operating system installations, application crashes, license activations, error popups, updates, browser bugs, and software configuration issues.
- **`access`**: Password resets, locked accounts, MFA token issues, SSO authentication failures, file/folder permissions, role-based access requests, joiner/mover/leaver account provisioning.
- **`email`**: Mailbox quotas, Outlook/webmail client issues, calendar synchronization and scheduling, shared mailboxes, distribution list management, spam/phishing reports, and email delivery failures.
- **`other`**: Inquiries fitting none of the above categories, general how-to questions, user training requests, audiovisual/conferencing assistance, facilities/furniture requests, or vague general inquiries.

### Priorities
- **`urgent`**: Site-wide or multi-user outage affecting business operations, mission-critical production service down, active security incident, or imminent data loss.
- **`high`**: Individual user or small team completely blocked with no viable workaround, or critical deadline/executive presentation at immediate risk.
- **`medium`**: Degraded performance, single-user malfunction with a temporary workaround, or non-blocking functional inconvenience.
- **`low`**: Standard service request, scheduled future change, cosmetic flaw, how-to inquiry, or informational question.

---

## 4. Generation & Curation Process

1. **Generation (12 Batches of 50)**:
   - Generated using LLM prompts targeting diverse operational environments (offices in Tokyo, London, New York, Chennai, Sydney), various personas (executives, developers, sales reps, customer service agents), and mixed difficulty tiers.
   - 100 tickets per category (50 in part 1, 50 in part 2):
     - `batch_01.jsonl` & `batch_02.jsonl`: `network` (NET-001 to NET-100)
     - `batch_03.jsonl` & `batch_04.jsonl`: `hardware` (HW-001 to HW-100)
     - `batch_05.jsonl` & `batch_06.jsonl`: `software` (SW-001 to SW-100)
     - `batch_07.jsonl` & `batch_08.jsonl`: `access` (ACC-001 to ACC-100)
     - `batch_09.jsonl` & `batch_10.jsonl`: `email` (EML-001 to EML-100)
     - `batch_11.jsonl` & `batch_12.jsonl`: `other` (OTH-001 to OTH-100)
   - ~26% hard cases (156 hard, 444 easy across 600 tickets).

2. **Automated Validation**:
   - Executed via `app/scripts/build_dataset.py`.
   - Every row is parsed and verified for non-empty fields, valid enumeration values, title >= 3 chars, description >= 10 chars, and global ID uniqueness.
   - Any malformed line is routed to `rejected.jsonl` with failure reason and line provenance.

3. **Near-Duplicate Detection & Grouping**:
   - Uses `HashingEmbedder` (`hashing-v2`, 4096 dimensions) to compute pairwise cosine similarity over `title + description`.
   - Connected components for pairs with cosine similarity > 0.85 are grouped together to prevent data leakage between splits.

4. **Human Review Sample**:
   - A 10% stratified random sample (60 tickets, 10 per category) was exported to `review_sample.csv` for human verification.
   - Corrections can be supplied in `review_corrections.csv` (`id`, `fix_category`, `fix_priority`) and applied automatically upon re-running the build pipeline.

5. **Train / Test Split**:
   - 80% train (480 tickets) and 20% test (120 tickets).
   - Group-aware and deterministic (`seed=42`).
   - Stratified across all 12 `(category, difficulty)` combinations: exactly 80 train and 20 test tickets for every category; exactly 354 easy and 126 hard in train, 90 easy and 30 hard in test.

---

## 5. Known Limitations

- **Synthetic Origin**: All tickets are synthetically generated by an LLM. While prompted to reflect authentic spelling errors, colloquial phrasing, and frustration levels, synthetic data may omit nuanced organizational slang, domain acronyms, or non-verbal ticket attachments present in real enterprise ITSM systems.
- **Single Generator Model**: Generated by a single family of models, which may introduce subtle stylistic consistencies or vocabulary distributions.
- **Subjective Ground Truth**: Labels reflect the generator's analytical judgement augmented by human sample review. In realistic IT service desks, edge cases (e.g., an Outlook crash caused by a full hard drive) can defensibly be classified as software, hardware, or email.
- **Absence of a Dedicated Security Category**: Security incidents (e.g. phishing, ex-employee access, firewall alerts) are partitioned into `access`, `email`, `network`, or `other` according to their primary system touchpoint.
- **Single Language**: The dataset is exclusively in English.

---

## 6. Intended Use

- **Intended Use**: Benchmarking and evaluating machine learning and heuristic models for automated ticket categorization, priority prediction, and duplicate detection.
- **Out of Scope**: Not intended as production training data for real-world automated resolution, nor as definitive statistical evidence of performance on proprietary, non-synthetic IT support queues.

