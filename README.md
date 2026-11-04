# ServiceDesk-AI

Role-based IT helpdesk ticketing application with business-hours SLA tracking, raw SQL reports, AI triage suggestions, and a modern React web UI served directly by FastAPI.

[![CI](https://github.com/praneeth-hari/ServiceDesk-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/praneeth-hari/ServiceDesk-AI/actions/workflows/ci.yml)
![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)
![React](https://img.shields.io/badge/React-19-61DAFB.svg)
![TypeScript](https://img.shields.io/badge/TypeScript-5.7-3178C6.svg)
![TailwindCSS](https://img.shields.io/badge/Tailwind-4.0-38B2AC.svg)
![MySQL 8](https://img.shields.io/badge/mysql-8.0-4479A1.svg)
![Tests](https://img.shields.io/badge/tests-166%20collected-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-96%25-brightgreen)
![License](https://img.shields.io/badge/license-MIT-green.svg)

---

## At a Glance

| Metric / Dimension | Specification |
| :--- | :--- |
| **API Endpoints** | 29 REST endpoints (`/api/v1`) |
| **Frontend UI** | Modern single-page app (React 19, TypeScript, Tailwind CSS, Vite) |
| **Serving Mode** | Unified service: FastAPI serves both the JSON REST API and the built SPA bundle |
| **Business Hours SLA** | 09:00–18:00 IST Monday–Friday, calendar-aware with holiday pauses |
| **Database Migrations** | 8 Alembic schema migration versions |
| **SQL Reports** | 9 raw SQL analytical reports (CTEs, `RANK()` window functions) |
| **CI Jobs** | 3 GitHub Actions jobs (Pytest & Coverage, MySQL 8 Migrations, Web Frontend) |

---

## Contents

- [Features](#features)
- [Architecture](#architecture)
- [Ticket Workflow](#ticket-workflow)
- [Database Schema](#database-schema)
- [AI Triage & Duplicate Detection](#ai-triage--duplicate-detection)
- [AI Triage Evaluation](#ai-triage-evaluation)
- [API Overview](#api-overview)
- [Quick Start](#quick-start)
- [Run with Docker](#run-with-docker)
- [Demo Data](#demo-data)
- [Testing & Quality](#testing--quality)
- [Design Decisions](#design-decisions)
- [Known Limitations](#known-limitations)
- [Project Structure](#project-structure)
- [License](#license)
- [Author](#author)

---

## Features

| Capability | Description |
| :--- | :--- |
| **Authentication & Roles** | JWT authentication with bcrypt hashing (72-byte limit validation). Three roles: `requester`, `agent`, and `admin`. |
| **Ticket Workflow** | Enforced state transitions (`open` -> `in_progress` <-> `waiting_on_requester`, `in_progress` -> `resolved` -> `closed`, with reopen). Invalid moves return 409. |
| **Business-Hours SLA** | SLA calculated strictly within operational hours (09:00–18:00 IST, Mon–Fri) and organization holidays. |
| **Pausable SLA Clock** | Moving to `waiting_on_requester` freezes the SLA clock (`sla_paused_at`); resuming to `in_progress` pushes `due_at` forward by exact elapsed business minutes. |
| **Holidays Management** | Admin CRUD API and web management (`/api/v1/holidays`), preventing SLA calculations on non-working dates. |
| **AI Triage & Duplicates** | Advisory category/priority suggestions via similarity-weighted kNN voting; duplicate detection over active tickets using L2-normalized cosine embeddings; real-time debounced suggestions in the web UI. |
| **AI Ticket Assist** | On-demand issue summary and draft reply assistance for agents via local Ollama (`AI_ASSIST_MODE=ollama`, off by default); strictly excludes internal notes, protects against prompt injection, and produces drafts for human review. |
| **Comments & History** | Public comments and staff-only `is_internal` notes. Full status change audit history recorded on state changes with author attribution. |
| **Search & Pagination** | Sanitized keyword search (`q`), multi-criteria filtering, multi-field sorting, and offset pagination. |
| **SQL Reports** | 9 raw SQL reports using aggregations, `LEFT JOIN`, Common Table Expressions (CTEs), and `RANK()` window functions. |
| **Web UI Portal** | Modern React + TypeScript SPA featuring pure-SVG SLA Runway timeline, sortable table, debounced AI triage, rich detail page with activity timeline, and reports charts. |

---

## Architecture

ServiceDesk-AI can run as a **single unified service** or in **development mode** with hot reload:

- **Unified / Production Mode**: FastAPI runs on port 8000 and serves both the REST API (`/api/v1/*`, `/docs`, `/redoc`) and the static production build of the React application (`web/dist/`). Client-side SPA routes fallback to `index.html` with `Cache-Control: no-cache` while static assets under `/assets` are cacheable.
- **Development Mode**: FastAPI runs the backend API on port 8000, while the Vite dev server runs the frontend on port 5173 with hot module replacement (HMR) and proxies API requests to `http://localhost:8000`.

```mermaid
flowchart TD
    subgraph Browser ["Web Browser"]
        UI["React SPA Client"]
    end

    subgraph Server ["Unified FastAPI Server (Port 8000)"]
        SPA["Static Files & SPA Catch-All (web/dist)"]
        Routes["FastAPI REST Routes (/api/v1)"]
        Services["Service Layer (Business Logic & Workflows)"]
        AI["AI Layer (HashingVectorizer / SBERT Embeddings)"]
        Models["SQLAlchemy 2.x Models"]
    end

    subgraph Data ["Data & CI"]
        DB[("MySQL 8 Database")]
        Alembic["Alembic Migrations (8 Versions)"]
        CI["GitHub Actions CI"]
    end

    UI -->|"Page & Assets (/, /assets/*)"| SPA
    UI -->|"HTTP / REST (JWT Auth)"| Routes
    Routes --> Services
    Services --> AI
    Services --> Models
    Models --> DB
    Alembic -.->|"Schema DDL"| DB
    CI -.->|"Automated Tests & Builds"| Server
```

---

## Ticket Workflow

The ticket lifecycle follows an explicit state transition machine managed entirely in the service layer.

```mermaid
stateDiagram-v2
    [*] --> open : Ticket Created
    open --> in_progress : Agent Assigned / Work Started
    in_progress --> waiting_on_requester : Pauses SLA Clock (Waiting for Requester)
    waiting_on_requester --> in_progress : Resumes SLA Clock (Pushes due_at by Business Minutes)
    in_progress --> resolved : Resolution Provided
    resolved --> closed : Requester / Admin Closes Ticket
    resolved --> in_progress : Reopened by Staff
    closed --> [*]
```

Any invalid or out-of-order state transition is rejected with an HTTP 409 Conflict status. Tickets in `waiting_on_requester` freeze the SLA clock and are never flagged as overdue while paused.

---

## Database Schema

The database consists of 6 tables managed via Alembic migrations.

```mermaid
erDiagram
    users {
        int id PK
        string email UK
        string full_name
        string hashed_password
        enum role
        boolean is_active
        datetime created_at
    }

    tickets {
        int id PK
        string title
        text description
        enum status
        enum priority
        enum category
        int requester_id FK
        int assignee_id FK
        datetime due_at
        datetime sla_paused_at
        datetime created_at
        datetime updated_at
        datetime resolved_at
    }

    holidays {
        int id PK
        date holiday_date UK
        string name
        datetime created_at
    }

    ticket_comments {
        int id PK
        int ticket_id FK
        int author_id FK
        text body
        boolean is_internal
        datetime created_at
    }

    ticket_status_history {
        int id PK
        int ticket_id FK
        int changed_by_id FK
        enum from_status
        enum to_status
        datetime created_at
    }

    ticket_embeddings {
        int ticket_id PK,FK
        string model_name
        int dim
        blob vector
        datetime updated_at
    }

    users ||--o{ tickets : "creates (requester)"
    users ||--o{ tickets : "assigned (assignee)"
    users ||--o{ ticket_comments : "authors"
    users ||--o{ ticket_status_history : "changes"
    tickets ||--o{ ticket_comments : "has"
    tickets ||--o{ ticket_status_history : "audits"
    tickets ||--o| ticket_embeddings : "embeds"
```

---

## AI Triage & Duplicate Detection

Automated category and priority suggestions and duplicate detection over ticket text using L2-normalized cosine embeddings.
Recommendations are strictly advisory and never mutate tickets automatically; agents and users retain full control.
Requesters only see evidence items and duplicate candidates from their own tickets, maintaining strict privacy isolation.
The service exposes `POST /api/v1/triage/suggest` (advisory triage and duplicates) and `GET /api/v1/tickets/{id}/similar` (staff only).
On the earlier small evaluation set (`data/triage_eval.csv`, 24 test tickets), category accuracy reached 58.33% vs 16.67% random chance (see [AI triage evaluation](#ai-triage-evaluation) below for the current benchmark on ServiceDesk-600).
Full details: [docs/AI_TRIAGE.md](docs/AI_TRIAGE.md).

### AI Ticket Assist (Summary & Draft Reply)

On the ticket detail page, support staff (`agent` and `admin` roles) can optionally invoke on-demand AI assist powered by local Ollama (`AI_ASSIST_MODE=ollama`, off by default):
- **Summarize**: Generates a concise summary of the issue and conversation history, extracting up to 4 key technical facts (error codes, OS, devices).
- **Draft reply**: Composes a polite, contextual draft reply addressing the requester, which agents can insert directly into the composer to edit and verify.
- **Privacy & Safety**: Internal notes (`is_internal=True`) are strictly excluded from LLM prompts. Nothing is persisted to the database, and no ticket content is logged. Outputs are advisory drafts for human review; no accuracy claims are made.

---

## AI triage evaluation

How well can the system suggest a ticket's category and priority? I built a labelled dataset and a reproducible benchmark to measure it, instead of guessing.

**Dataset (ServiceDesk-600).** 600 synthetic IT service desk tickets (100 per category, about 26% deliberately hard or ambiguous) written with Claude Opus 5.5, then validated, de-duplicated and split 480 train / 120 test with whole near-duplicate groups kept on one side. Labels were audited: a 60-ticket sample was reviewed by a second model and a human, 7 priority labels were corrected, and a pattern found in that audit (simple questions labelled `medium` instead of `low`) led to 20 more corrections. See [data/servicedesk600/DATASET.md](data/servicedesk600/DATASET.md).

**Results on the 120 held-out test tickets** (95% Wilson interval in brackets):

| Method | Category accuracy | Priority accuracy | Priority within one level | Time per ticket |
| :--- | :--- | :--- | :--- | :--- |
| Llama 3.1 8B + 5 retrieved examples | **87.5%** [80.4, 92.3] | **69.2%** | 98.3% | 2.4 s |
| Qwen 2.5 3B + 5 retrieved examples | 83.3% [75.6, 88.9] | 60.0% | 95.8% | 0.44 s |
| Qwen 2.5 3B zero-shot | 80.8% [72.9, 86.9] | 55.8% | 95.8% | 0.36 s |
| Llama 3.1 8B zero-shot | 79.2% [71.0, 85.5] | 68.3% | 99.2% | 2.1 s |
| MiniLM embeddings + kNN | 76.7% [68.3, 83.3] | 47.5% | 85.0% | 1 ms |
| bge-small embeddings + kNN | 69.2% [60.4, 76.7] | 45.0% | 88.3% | 1 ms |
| hashing-v2 + kNN (the triage the app ships today) | 62.5% [53.6, 70.7] | 44.2% | 81.7% | 1 ms |
| Majority class | 16.7% | 33.3% | 80.8% | - |

**What the results show**
- Llama 3.1 8B with retrieved examples is significantly better at category than both the shipped lexical baseline (paired McNemar exact test, p < 0.001) and MiniLM embeddings (p = 0.011).
- Retrieving similar labelled tickets helps the LLM: category accuracy rises from 79.2% to 87.5% for Llama 3.1 8B.
- LLMs are far better than nearest-neighbour methods at priority (about 68-69% against 44-48%), which fits the idea that priority depends on impact, not on wording.
- The 3B model is within about 4 points of the 8B model on category at roughly one sixth of the latency, but with 120 test tickets the intervals overlap, so this is not a statistically established difference.
- Category errors of the best method concentrate on software/hardware and other/network boundaries; `email` had no errors. Priority errors are balanced (20 over-predicted, 17 under-predicted), and nearly all are off by one level.

**Limits.** The data is synthetic and from a single generator model; the test set is small (about +/-6-8 points); the LLM prompts include the written category and priority definitions; each result is a single deterministic run (temperature 0, seed 42); and some labels are genuinely ambiguous (for example, a ticket about typing a password into a phishing page is labelled `access`, though the definitions also put phishing under `email`). The test labels were not changed after seeing model results. The LLM methods run locally through Ollama and can be enabled via `AI_TRIAGE_MODE=llm`; by default, the app ships the lightweight hashing triage. Full tables, confusion matrices, failure examples and dataset hashes are in [benchmarks/RESULTS.md](benchmarks/RESULTS.md).

**Reproduce**

    pip install -r requirements-bench.txt
    python -m app.scripts.build_dataset
    python -m app.scripts.benchmark_triage --methods hashing-knn,minilm-knn,bge-small-knn
    python -m app.scripts.benchmark_triage --methods llm-zero-shot,llm-rag --model llama3.1:8b
    python -m app.scripts.benchmark_triage --methods llm-zero-shot,llm-rag --model qwen2.5:3b


### LLM-assisted triage (optional, local)

While ServiceDesk-AI defaults to instant lexical kNN triage, you can optionally enable local LLM-assisted triage powered by Ollama:

1. Install [Ollama](https://ollama.com/) and pull the target model:
   ```bash
   ollama pull llama3.1:8b
   ```
2. Enable LLM mode in your `.env`:
   ```bash
   AI_TRIAGE_MODE=llm
   OLLAMA_BASE_URL=http://127.0.0.1:11434
   AI_LLM_MODEL=llama3.1:8b
   AI_LLM_TIMEOUT_SECONDS=30
   AI_LLM_EXAMPLES=5
   ```

- **Resilience & Graceful Fallback**: If Ollama is unreachable, times out, the target model is not installed, or the LLM returns malformed JSON or labels outside the allowed taxonomy, the triage service silently and instantly falls back to lexical kNN. The triage API endpoint never fails (never returns 5xx) because the local LLM is down. The response marks `method: "knn"` and includes `fallback_reason`.
- **Hosted Demo vs. Local Mode**: In the hosted demo and standard container deployment, triage runs in pure kNN mode (zero GPU, zero external network calls, <10ms response time).
- **Benchmark Performance**: On the ServiceDesk-600 test split (120 tickets), the exact production pipeline (`llm-rag-hashing`: native hashing retrieval + Llama 3.1 8B 5-shot RAG) achieves **85.8%** category accuracy (64.2% priority accuracy, 96.7% within one level); paired McNemar exact test against dense MiniLM retrieval ($b=7$ where `llm-rag` is correct and `llm-rag-hashing` is wrong, $c=5$ where `llm-rag-hashing` is correct and `llm-rag` is wrong, $p = 0.774$): no difference was detected (12 discordant pairs; the test cannot show equivalence).
- **Prompt Injection Defense**: When LLM triage is enabled, incoming ticket text is protected by a two-tier defense:
  1. *Deterministic Heuristic Guard (`app/ai/injection_guard.py`)*: Detects instruction overrides, role impersonation, and format breaks. On detection, bypasses the LLM and falls back to kNN similarity (`fallback_reason = "possible_prompt_injection"`). Verified **0.0%** false positives across 220 clean benchmark tickets (95% CI: [0.0%, 1.7%]).
  2. *Prompt Boundary Isolation (`app/ai/llm_triage.py` v2)*: Wraps ticket text in `<ticket_data>` tags and escapes angle brackets (`<` -> `&lt;`, `>` -> `&gt;`). A paired exact McNemar test on the 120 clean test tickets shows **no statistically significant difference** in category accuracy between Prompt V1 and V2 (p = 0.0923 for zero-shot, p = 1.000 for RAG).
  - *Empirical Robustness*:
    - **Independent held-out set v2 ($N=30$, authored independently outside workflow, run once)**:
      - Heuristic guard detection was **11/30 (36.7%)** [21.9%, 54.5%], missing 19 novel attacks due to phrasing variance and leetspeak.
      - Full-defense attack success was **2/30 (6.7%)** [1.8%, 21.3%] vs. kNN **4/30 (13.3%)** [5.3%, 29.7%], with overlapping intervals (**comparable to kNN**).
      - kNN keyword-stuffing weakness: Under lexical keyword stuffing (`lexical_stuffing`), pure `hashing-knn` succumbed with **4/5 (80.0%)** attack success rate, while the full LLM defense resisted completely (**0/5, 0.0%**).
    - **In-workflow held-out set v1 ($N=30$, frozen by process, not independent)**: Attacked ASR drops from **63.3%** to **13.3%** (4/30 [5.3%, 29.7%]), which is **comparable to kNN** at **20.0%** (6/30 [9.5%, 37.3%]) with overlapping intervals.
    - **Development set ($N=40$, tuned on this set)**: Attacked Attack Success Rate (ASR) drops from **55.0%** (22/40) to **2.5%** (1/40) with full defense.
  - *Limits*: Small samples ($N=30, 40$), heuristic regex detection can be evaded by paraphrasing and other languages, benchmarked on local 8B model only, lexical keyword stuffing against kNN is not addressed by the guard, and all triage outputs are advisory suggestions that a human reviews. See [benchmarks/INJECTION.md](benchmarks/INJECTION.md).
---

## API Overview

All routes are prefixed with `/api/v1`. Interactive documentation is available at `/docs` (Swagger UI) and `/redoc` (ReDoc). The API exposes **29 REST endpoints**:

<details>
<summary>All 29 endpoints (click to expand)</summary>

| Method | Endpoint | Description | Access |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/register` | Register a new user account (defaults to requester role) | Public |
| `POST` | `/api/v1/auth/login` | Authenticate with email and password, returning JWT access token | Public |
| `GET` | `/api/v1/users/me` | Retrieve profile of the currently authenticated user | Authenticated |
| `GET` | `/api/v1/users` | List registered users with pagination parameters | Admin |
| `PATCH` | `/api/v1/users/{id}/role` | Update role of a specific user | Admin |
| `POST` | `/api/v1/tickets` | Create a new support ticket (calculates business-hours SLA `due_at`) | Authenticated |
| `GET` | `/api/v1/tickets` | List tickets with filters (status, priority, category, assignee, overdue), search, and pagination | Authenticated |
| `GET` | `/api/v1/tickets/{id}` | Get ticket details (returns 404 if accessed by foreign requester) | Authenticated |
| `PATCH` | `/api/v1/tickets/{id}` | Update title, description, priority, or category | Owner (open) / Agent (category) / Admin |
| `PATCH` | `/api/v1/tickets/{id}/status` | Transition status (pauses SLA clock on `waiting_on_requester`; pushes `due_at` on resume) | Agent / Admin |
| `PATCH` | `/api/v1/tickets/{id}/assign` | Assign ticket to an agent (transitions open -> in_progress) | Agent / Admin |
| `GET` | `/api/v1/tickets/{id}/comments` | List ticket comments (internal notes hidden from requesters) | Owner / Agent / Admin |
| `POST` | `/api/v1/tickets/{id}/comments` | Add comment (staff can set `is_internal=true`) | Owner / Agent / Admin |
| `GET` | `/api/v1/tickets/{id}/history` | Retrieve full status transition history audit trail | Owner / Agent / Admin |
| `GET` | `/api/v1/tickets/{id}/similar` | Retrieve tickets similar to a specific ticket, excluding itself (optional `?limit=`) | Agent / Admin |
| `POST` | `/api/v1/triage/suggest` | Advisory category/priority suggestions and duplicate detection | Authenticated |
| `GET` | `/api/v1/holidays` | List registered organization holidays, ordered by date (optional `?year=`) | Agent / Admin |
| `POST` | `/api/v1/holidays` | Register an organization holiday date (409 on duplicate date) | Admin |
| `DELETE` | `/api/v1/holidays/{id}` | Remove an organization holiday by ID (404 if missing) | Admin |
| `GET` | `/api/v1/reports/tickets-by-status` | Aggregated ticket counts grouped by status and priority | Agent / Admin |
| `GET` | `/api/v1/reports/overdue` | List overdue tickets past SLA due date with requester and assignee (excludes paused) | Agent / Admin |
| `GET` | `/api/v1/reports/resolution-time` | Average resolution hours per agent calculated via CTE | Agent / Admin |
| `GET` | `/api/v1/reports/agent-ranking` | Agent performance ranking calculated via `RANK()` function | Agent / Admin |
| `GET` | `/api/v1/reports/daily-volume` | Daily creation volume over a configurable window (1–90 days) | Agent / Admin |
| `GET` | `/api/v1/reports/sla-breach-rate` | SLA breach rate and compliance counts per ticket priority (paused tickets not overdue) | Agent / Admin |
| `GET` | `/api/v1/reports/resolution-time-by-category` | Average resolution hours grouped by category and priority | Agent / Admin |
| `GET` | `/api/v1/reports/agent-workload` | Agent workload summary: open work, overdue tickets, and resolved counts | Agent / Admin |
| `GET` | `/api/v1/reports/tickets-by-category` | Ticket counts grouped by category, optionally broken down by status | Agent / Admin |
| `GET` | `/api/v1/health` | Health check endpoint confirming API and database connectivity | Public |

</details>

---

## Quick Start

Follow these steps to run ServiceDesk-AI locally on Windows PowerShell.

### 1. Clone the repository

```powershell
git clone https://github.com/praneeth-hari/ServiceDesk-AI.git
cd ServiceDesk-AI
```

### 2. Create and activate a virtual environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt -r requirements-dev.txt
```

> **Optional**: To enable the optional dense semantic embedding backend (`sbert` / `sentence-transformers`), also install:
>
> ```powershell
> pip install -r requirements-ai.txt
> ```
>
> **Benchmarks**: Reproducing the AI triage benchmarks uses `requirements-bench.txt` (optional, local only, not in the Docker image or CI):
>
> ```powershell
> pip install -r requirements-bench.txt
> ```

### 4. Configure environment variables

```powershell
Copy-Item .env.example .env
```

Key configuration settings (with default values):

- `DATABASE_URL`: Connection string for MySQL 8 (`mysql+pymysql://helpdesk:helpdesk_password@localhost:3306/helpdesk_db`)
- `SECRET_KEY`: Secret string for HMAC-SHA256 JWT encoding
- `WORK_TIMEZONE`: Timezone for working hours evaluation (default: `Asia/Kolkata`)
- `WORK_DAY_START`: Working day operational start time (default: `09:00`)
- `WORK_DAY_END`: Working day operational end time (default: `18:00`)
- `WORK_DAYS`: Operational days as JSON list of integers 0=Mon..6=Sun (default: `[0, 1, 2, 3, 4]`)
- `WEB_DIST_DIR`: Path to built web assets directory (default: `web/dist`)

### 5. Start MySQL database container

```powershell
docker compose up -d db
```

### 6. Run database migrations

```powershell
alembic upgrade head
```

### 7. Populate demo data or create an administrator account

To populate 36 realistic demo tickets with relative timestamps, audit history, comments, and AI embeddings:

```powershell
python -m app.scripts.seed_demo --yes
# or: python scripts/seed_demo.py --yes
```

To create a separate administrator account:

```powershell
python -m app.scripts.create_admin --email admin@example.com --password AdminPassword123! --name "System Admin"
```

### 8. Run the Application

You can run ServiceDesk-AI in either of two modes:

#### Mode A: Unified Production-Style Service (Single Service on Port 8000)

FastAPI serves both the REST API and the built React frontend application from a single process:

```powershell
# Step A1: Build the React web frontend bundle
cd web
npm install
npm run build
cd ..

# Step A2: Start FastAPI server
python -m uvicorn app.main:app --port 8000
```

Open [http://localhost:8000](http://localhost:8000) in your browser. Both the web interface and the API (`/api/v1/*`) are served together.

#### Mode B: Development Mode (Hot Reloading Frontend & Backend)

For active frontend or backend development:

**Terminal 1 (Backend API):**
```powershell
.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --port 8000
```

**Terminal 2 (Web Frontend with Vite HMR):**
```powershell
cd web
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser (API calls are proxied automatically to `http://localhost:8000`).

---

## Run with Docker

You can build and run the entire application (FastAPI backend + built React frontend) as a single container using the production multi-stage `Dockerfile`:

### 1. Build the Docker image

```powershell
docker build -t servicedesk-ai .
```

### 2. Run the container

Provide your database URL and a strong secret key (at least 32 characters in production) via environment variables, and map the port:

```powershell
docker run -d `
  --name servicedesk-app `
  -p 8000:8000 `
  -e DATABASE_URL="mysql+pymysql://helpdesk:helpdesk_password@host.docker.internal:3306/helpdesk_db" `
  -e SECRET_KEY="your-secure-random-secret-key-at-least-32-chars-long" `
  servicedesk-ai
```

> **Note on Port Configuration**: If port 8000 is busy or blocked on your host, use another host port in the port mapping (e.g., `-p 8010:8000` to access the service at `http://localhost:8010`), or specify a custom container port via the `PORT` environment variable (e.g., `-e PORT=8010 -p 8010:8010`). Similarly, when running `uvicorn` directly outside Docker, pass `--port 8010`.

---

## Demo Data

To populate the database with 36 realistic demo tickets spread across the last 3 weeks with authentic timestamps relative to current time, covering all SLA lifecycle states (on track, at risk, breached, clock paused, resolved within SLA, resolved after breach, and closed), run the demo seed script:

```powershell
# 1. Preview what would be created without touching the database
python -m app.scripts.seed_demo --dry-run
# or: python scripts/seed_demo.py --dry-run

# 2. Seed demo tickets (safe: only adds tickets, never touches users or holidays)
python -m app.scripts.seed_demo --yes
# or: python scripts/seed_demo.py --yes

# 3. Wipe demo tickets, comments, status history, and embeddings (requires --yes confirmation)
python -m app.scripts.seed_demo --wipe-tickets --yes
# Note: running --wipe-tickets without --yes is safe and only reports what would be deleted
```

- **`--dry-run`**: Inspects current calendar and business hours (09:00–18:00 IST) and displays a formatted summary table of all 36 tickets, priorities, categories, SLA states, and comments that would be written, without making any database changes.
- **`--wipe-tickets`**: Deletes all tickets, comments, status history, and embedding rows. For safety, it **requires `--yes`**; omitting `--yes` only prints the count of rows that would be deleted and exits cleanly without modifying the database. It never deletes users or holidays.
- **`--yes` / `-y`**: Confirms execution of database writes or wipe operations.

### Demo Accounts

| Role | Email | Password | Full Name |
| :--- | :--- | :--- | :--- |
| **Admin** | `admin@example.com` | `AdminPassword123!` | System Admin |
| **Agent** | `agent@example.com` | `AgentPassword123!` | Asha Agent |
| **Requester** | `requester@example.com` | `RequesterPassword123!` | Ravi Requester |

> [!WARNING]
> **Local Development Security Warning**: These demo accounts and default passwords in `.env.example` and `docker-compose.yml` are strictly intended for local development, demonstration, and automated test environments. **Never deploy these default passwords in production.**

---

## Testing & Quality

Run backend tests with coverage reporting:

```powershell
pytest --cov=app --cov-report=term-missing --cov-fail-under=85
```

Run frontend linting, tests, and production build:

```powershell
cd web
npm run lint
npm test
npm run build
cd ..
```

GitHub Actions CI runs the full test suite with coverage enforcement, executes MySQL 8 migration checks (`upgrade -> downgrade -> upgrade`), and builds and tests the React frontend on every push and pull request.

---

## Design Decisions

- **Unified Single-Service Deployment**: In production-style operation, FastAPI mounts `web/dist` static assets and serves client-side SPA routes fallback to `index.html` with `Cache-Control: no-cache`, eliminating the need for a separate web server while preventing path traversal and protecting API routes.
- **404 Instead of 403 for Foreign Tickets**: Requesters attempting to view another user's ticket receive a 404 Not Found rather than 403 Forbidden to prevent ticket ID enumeration.
- **Requester Identity Bound to JWT**: The `requester_id` is always extracted from the authenticated user token, preventing users from creating tickets on behalf of others.
- **Service-Layer State Machine**: Status transitions are defined centrally in `app/services/tickets.py` rather than within routes, guaranteeing uniform business rule enforcement.
- **Business-Hours SLA & Pausable Clock**: SLA deadlines (`due_at`) are calculated strictly during operational business hours (09:00–18:00 IST), skipping off-hours, weekends, and database-registered holidays. Transitioning a ticket to `waiting_on_requester` pauses the SLA clock by setting `sla_paused_at`, removing it from overdue queries. Returning to `in_progress` computes exact elapsed business minutes and shifts `due_at` forward proportionally.
- **Advisory AI Triage & Privacy**: Category and priority suggestions use similarity-weighted k-Nearest Neighbours over historically resolved tickets. Recommendations never auto-mutate tickets; requesters only see their own tickets in evidence and duplicate candidate lists.
- **Bcrypt 72-Byte Limit Validation**: Pydantic validators explicitly check the UTF-8 byte length (maximum 72 bytes) before passing passwords to bcrypt, avoiding silent password truncation.
- **Dual-Engine Test Strategy**: Local unit tests run against fast in-memory SQLite (`sqlite:///:memory:`) for sub-second execution, while CI executes against MySQL 8 to validate SQL window functions and migrations.
- **Correlation Request-ID Logging**: Middleware extracts or generates an `X-Request-ID` stored in `contextvars`, including it in all log entries across the request lifecycle without logging sensitive tokens or passwords.

---

## Known Limitations

- **Lexical vs. Semantic AI Triage**: The default `hashing-v2` backend uses sublinear-scaled word n-grams (with stop words removed) and character 3-5 n-grams (dim=4096). On the earlier small evaluation set, category accuracy reached 58.33% with 100% suggestion coverage at threshold 0.12 (see [AI triage evaluation](#ai-triage-evaluation) for the current benchmark on ServiceDesk-600 where it scores 62.5% vs 87.5% for LLM-RAG). sbert is supported as an optional pluggable embedder (`requirements-ai.txt`) but requires additional dependencies.
- **Offset Pagination**: Pagination uses standard SQL `LIMIT` / `OFFSET`, which is straightforward for moderate datasets but less performant on massive tables than keyset pagination.
- **User Roster Access**: Only admins can list users; agents must input target agent IDs manually when assigning tickets.
- **No Email Notifications**: Ticket lifecycle events and comments are tracked in database history rather than sending outbound email alerts.

---

## Project Structure

```text
.
├── alembic/              # Database migration configuration and version scripts (8 revisions)
├── app/                  # FastAPI backend application core, models, schemas, and routes
│   ├── ai/               # AI embedder protocols, HashingVectorizer, and SBERT backends
│   ├── api/              # API route definitions and dependency injection (29 endpoints)
│   ├── core/             # Configuration, logging middleware, security, and SLA definitions
│   ├── db/               # Database engine, session management, and Base declarative model
│   ├── models/           # SQLAlchemy entity models (6 tables) and enums (3 roles)
│   ├── schemas/          # Pydantic models for validation and response serialization
│   ├── scripts/          # Administrative CLI utilities (admin, demo seed, reindex, eval)
│   └── services/         # Business logic layer (tickets workflow, reports, auth, triage)
├── data/                 # Benchmark evaluation dataset (synthetic helpdesk tickets)
├── docs/                 # Documentation assets
├── scripts/              # Helper entrypoints (seed_demo.py)
├── tests/                # Automated pytest test suites (166 collected tests)
├── web/                  # Web frontend application (React 19, TypeScript, Vite, Tailwind 4)
├── docker-compose.yml    # Multi-container orchestration for MySQL 8 and backend
├── Dockerfile            # Container build specification for FastAPI app
├── LICENSE               # MIT License
├── pytest.ini            # Pytest configuration and coverage settings
├── requirements.txt      # Production runtime dependencies
├── requirements-ai.txt   # Optional semantic embedding dependencies (sentence-transformers)
├── requirements-bench.txt # Optional benchmark dependencies (sentence-transformers, local only)
├── requirements-dev.txt  # Development and testing dependencies
└── README.md             # Project documentation
```

---

## License

This project is licensed under the [MIT License](LICENSE) - see the [LICENSE](LICENSE) file for details.

---

## Author

Hari Praneeth (github.com/praneeth-hari)
