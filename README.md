# HelpDesk API

Role-based IT helpdesk ticketing REST API with business-hours SLA tracking, raw SQL reports, AI triage suggestions, and a Streamlit dashboard.

[![CI](https://github.com/pasupunuri-pragnitha/HelpDesk-API/actions/workflows/ci.yml/badge.svg)](https://github.com/pasupunuri-pragnitha/HelpDesk-API/actions/workflows/ci.yml)
![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)
![MySQL 8](https://img.shields.io/badge/mysql-8.0-4479A1.svg)
![Tests](https://img.shields.io/badge/tests-181%20collected-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-96%25-brightgreen)
![License](https://img.shields.io/badge/license-MIT-green.svg)

---

## At a Glance

| Metric / Dimension | Specification |
| :--- | :--- |
| **API Endpoints** | 29 REST endpoints (`/api/v1`) |
| **Test Suite** | 181 collected tests (177 passed, 4 skipped without MySQL / optional dependencies) |
| **Code Coverage** | 96% statement coverage (`app`) |
| **Database Migrations** | 8 Alembic schema migration versions |
| **SQL Reports** | 9 raw SQL analytical reports (CTEs, `RANK()` window functions) |
| **CI Jobs** | 2 GitHub Actions jobs (Pytest & Coverage, MySQL 8 Migrations & Integration) |

---

## Contents

- [Features](#features)
- [Architecture](#architecture)
- [Ticket Workflow](#ticket-workflow)
- [Database Schema](#database-schema)
- [AI Triage & Duplicate Detection](#ai-triage--duplicate-detection)
- [API Overview](#api-overview)
- [Quick Start](#quick-start)
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
| **Business-Hours SLA** | SLA calculated strictly within configurable working hours (`WORK_TIMEZONE`, `WORK_DAY_START`, `WORK_DAY_END`, `WORK_DAYS`) and organization holidays. |
| **Pausable SLA Clock** | Moving to `waiting_on_requester` freezes the SLA clock (`sla_paused_at`); resuming to `in_progress` pushes `due_at` forward by exact elapsed business minutes. |
| **Holidays Management** | Admin CRUD API for organizational holiday calendars (`/api/v1/holidays`), preventing SLA calculations on non-working dates. |
| **AI Triage & Duplicates** | Advisory category/priority suggestions via similarity-weighted kNN voting; duplicate detection over active tickets using L2-normalized cosine embeddings; interactive Streamlit dashboard support with on-demand suggestions, duplicate alerts, and staff-only similar ticket discovery. |
| **Comments & History** | Public comments and staff-only `is_internal` notes. Full status change audit history recorded on state changes. |
| **Search & Pagination** | Sanitized keyword search (`q`), multi-criteria filtering, multi-field sorting, and offset pagination. |
| **SQL Reports** | 9 raw SQL reports using aggregations, `LEFT JOIN`, Common Table Expressions (CTEs), and `RANK()` window functions. |
| **Streamlit Dashboard** | Complete management portal covering tickets list, new ticket AI triage, ticket details with audit trail, holiday calendar management, and KPI analytics. |

---

## Architecture

The system uses a layered architecture separating transport, business logic, persistence, and presentation.

```mermaid
flowchart TD
    Client["Streamlit Dashboard (Port 8501)"] -->|"HTTP / REST (JWT Auth)"| Routes["FastAPI Routes (/api/v1)"]
    Routes --> Services["Service Layer (Business Logic & Workflows)"]
    Services --> AI["AI Layer (HashingVectorizer / SBERT Embeddings)"]
    Services --> Models["SQLAlchemy 2.x Models"]
    Models --> DB[("MySQL 8 Database")]
    Alembic["Alembic Migrations (8 Versions)"] -.->|"Schema DDL"| DB
    CI["GitHub Actions CI"] -.->|"Automated Tests & Migration Check"| Routes
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
On the benchmark dataset (`data/triage_eval.csv`, synthetic tickets), category accuracy reaches 58.33% vs 16.67% random chance.
Full details: [docs/AI_TRIAGE.md](docs/AI_TRIAGE.md).

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

Follow these steps to run the API and Streamlit dashboard locally on Windows PowerShell.

### 1. Clone the repository

```powershell
git clone https://github.com/pasupunuri-pragnitha/HelpDesk-API.git
cd HelpDesk-API
```

### 2. Create and activate a virtual environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt -r requirements-dev.txt
pip install -r dashboard/requirements.txt
```

> **Optional**: To enable the optional dense semantic embedding backend (`sbert` / `sentence-transformers`), also install:
>
> ```powershell
> pip install -r requirements-ai.txt
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

### 5. Start MySQL database container

```powershell
docker compose up -d db
```

### 6. Run database migrations

```powershell
alembic upgrade head
```

### 7. Create an administrator account or populate demo data

To create an administrator account:

```powershell
python -m app.scripts.create_admin --email admin@example.com --password AdminPassword123! --name "System Admin"
```

Or populate realistic demo data across all workflows, reports, and AI triage embeddings:

```powershell
python -m app.scripts.seed_demo --yes
```

### 8. Run the FastAPI backend

In Terminal 1:

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

### 9. Run the Streamlit dashboard

In a separate PowerShell terminal (Terminal 2):

```powershell
.venv\Scripts\Activate.ps1
python -m streamlit run dashboard/app.py
```

The dashboard will open automatically in your browser at `http://localhost:8501`. For detailed dashboard documentation, see [dashboard/README.md](dashboard/README.md).

---

## Demo Data

To populate the database with realistic sample tickets across all 6 categories, 4 priorities, workflow statuses (including `waiting_on_requester`), public/internal comments, and overdue SLA scenarios, run the demo seed script:

```powershell
# Using the safety confirmation flag
python -m app.scripts.seed_demo --yes

# Or via environment variable
$env:ALLOW_DEMO_SEED="1"
python -m app.scripts.seed_demo
```

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

Run the test suite locally with coverage reporting:

```powershell
pytest --cov=app --cov-report=term-missing --cov-fail-under=85
```

GitHub Actions CI runs the full test suite with coverage enforcement and executes MySQL 8 migration checks (`upgrade -> downgrade -> upgrade`) on every push and pull request.

---

## Design Decisions

- **404 Instead of 403 for Foreign Tickets**: Requesters attempting to view another user's ticket receive a 404 Not Found rather than 403 Forbidden to prevent ticket ID enumeration.
- **Requester Identity Bound to JWT**: The `requester_id` is always extracted from the authenticated user token, preventing users from creating tickets on behalf of others.
- **Service-Layer State Machine**: Status transitions are defined centrally in `app/services/tickets.py` rather than within routes, guaranteeing uniform business rule enforcement.
- **Business-Hours SLA & Pausable Clock**: SLA deadlines (`due_at`) are calculated strictly during operational business hours, skipping off-hours, weekends, and database-registered holidays. Transitioning a ticket to `waiting_on_requester` pauses the SLA clock by setting `sla_paused_at`, removing it from overdue queries. Returning to `in_progress` computes exact elapsed business minutes and shifts `due_at` forward proportionally.
- **Advisory AI Triage & Privacy**: Category and priority suggestions use similarity-weighted k-Nearest Neighbours over historically resolved tickets. Recommendations never auto-mutate tickets; requesters only see their own tickets in evidence and duplicate candidate lists.
- **Bcrypt 72-Byte Limit Validation**: Pydantic validators explicitly check the UTF-8 byte length (maximum 72 bytes) before passing passwords to bcrypt, avoiding silent password truncation.
- **Dual-Engine Test Strategy**: Local unit tests run against fast in-memory SQLite (`sqlite:///:memory:`) for sub-second execution, while CI executes against MySQL 8 to validate SQL window functions and migrations (which caught a real MySQL-only downgrade bug in migration 0002).
- **Correlation Request-ID Logging**: Middleware extracts or generates an `X-Request-ID` stored in `contextvars`, including it in all log entries across the request lifecycle without logging sensitive tokens or passwords.

---

## Known Limitations

- **Lexical vs. Semantic AI Triage**: The default `hashing-v2` backend uses sublinear-scaled word n-grams (with stop words removed) and character 3-5 n-grams (dim=4096). On our benchmark dataset, category accuracy reaches 58.33% with 100% suggestion coverage (at threshold 0.12). sbert is supported as an optional pluggable embedder (requirements-ai.txt) but has not been measured on this dataset.
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
├── dashboard/            # Streamlit web portal client and analytics views
│   └── views/            # Screen views (login, tickets, new ticket, detail, holidays, reports)
├── data/                 # Benchmark evaluation dataset (synthetic helpdesk tickets)
├── docs/                 # Documentation assets
├── tests/                # Automated pytest test suites (181 collected tests)
│   └── dashboard/        # Dashboard API client, formatting, and smoke tests
├── docker-compose.yml    # Multi-container orchestration for MySQL 8 and backend
├── Dockerfile            # Container build specification for FastAPI app
├── LICENSE               # MIT License
├── pytest.ini            # Pytest configuration and coverage settings
├── requirements.txt      # Production runtime dependencies
├── requirements-ai.txt   # Optional semantic embedding dependencies (sentence-transformers)
├── requirements-dev.txt  # Development and testing dependencies
└── README.md             # Project documentation
```

---

## License

This project is licensed under the [MIT License](LICENSE) - see the [LICENSE](LICENSE) file for details.

---

## Author

Pasupunuri Pragnitha

- GitHub: [pasupunuri-pragnitha](https://github.com/pasupunuri-pragnitha)  
- LinkedIn: [pragnitha-pasupunuri](https://www.linkedin.com/in/pragnitha-pasupunuri)
