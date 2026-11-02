# Synthetic IT Helpdesk Triage Evaluation Dataset

This dataset (`data/triage_eval.csv`) contains 120 **synthetic demo tickets** across 6 support categories (`network`, `hardware`, `software`, `access`, `email`, `other`) and 4 priority levels (`low`, `medium`, `high`, `urgent`).

> [!NOTE]
> All tickets in this dataset are entirely synthetic and generated for evaluating the kNN triage and classification models. They do not represent real customer, user, or company data.

## Schema

- `title`: Short summary of the technical problem or request.
- `description`: Detailed symptoms, error messages, and context.
- `category`: Ground-truth category (`network`, `hardware`, `software`, `access`, `email`, `other`).
- `priority`: Ground-truth priority (`low`, `medium`, `high`, `urgent`).
