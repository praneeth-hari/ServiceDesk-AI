# Tickets Feature Contract & Implementation Notes

## Backend Contract Findings (GET /api/v1/tickets)

### Response Shape & Paging Envelope
The endpoint returns a `PaginatedTickets` object:
- `items`: array of `TicketRead` objects
- `total`: total count matching current filters
- `page`: current page (1-indexed)
- `page_size`: items per page (default 20, maximum 100)

### Field Names & Types
- `id` (`number`): unique ticket identifier
- `title` (`string`): ticket summary
- `description` (`string`): ticket description
- `status` (`'open' | 'in_progress' | 'waiting_on_requester' | 'resolved' | 'closed'`): current workflow status
- `priority` (`'low' | 'medium' | 'high' | 'urgent'`): priority level
- `category` (`'network' | 'hardware' | 'software' | 'access' | 'email' | 'other'`): ticket category
- `requester_id` (`number`): ID of requesting user
- `requester_name` (`string | null`): full name of requester
- `assignee_id` (`number | null`): ID of assigned agent (or null if unassigned)
- `assignee_name` (`string | null`): full name of assigned agent (or null if unassigned)
- `created_at` (`string`, ISO 8601 UTC): ticket creation timestamp
- `updated_at` (`string`, ISO 8601 UTC): last modification timestamp
- `due_at` (`string | null`, ISO 8601 UTC): business-hours SLA due timestamp calculated upon creation and shifted on SLA resume
- `sla_paused_at` (`string | null`, ISO 8601 UTC): timestamp when ticket was moved to `waiting_on_requester`, pausing the SLA clock
- `is_overdue` (`boolean`): computed flag returning `true` only if `due_at < now`, status is `open` or `in_progress`, and SLA is not currently paused

### Fields Not in API
1. **`resolved_at`**: The database and `TicketRead` schema have no `resolved_at` column. For resolved/closed tickets, resolution timestamp is represented by `updated_at`.
2. **Remaining / Elapsed SLA Time**: The API does not compute or return remaining business minutes or elapsed business hours. Remaining and elapsed business times are computed in the frontend using `businessTime.ts`.

### Backend Query Filters & Sorting
- Supported query parameters: `page`, `page_size`, `status`, `priority`, `category`, `assignee_id`, `overdue`, `q` (keyword search across title/description), `sort_by` (`'created_at' | 'updated_at' | 'due_at'`), and `order` (`'asc' | 'desc'`).
- In Table view, sorting by SLA maps to backend `sort_by=due_at`. Table sorting by ID is handled via client-side sort on the loaded page as `id` is not an exposed `sort_by` enum in the backend route.
- In Filter row, Status, Priority, Assignee (`assignee_id`), and search box (`q`) are passed directly as backend query parameters.

### Holidays & Work Hours Limitation
- Work hours are configured as 09:00 to 18:00, Monday through Friday, in timezone `Asia/Kolkata` (UTC+05:30).
- `GET /api/v1/holidays` is restricted to staff (`agent` and `admin` roles) and returns HTTP 403 Forbidden for `requester`. As instructed, client-side business time calculations ignore organizational holidays to ensure uniform behavior for all user roles without unauthorized API calls.



---

## New Ticket and Triage Contract Findings

### POST /api/v1/tickets (Create Ticket)
- **Request Body (`TicketCreate`)**:
  - `title` (`string`, required): min 1, max 255 characters.
  - `description` (`string`, required): min 1 character.
  - `priority` (`'low' | 'medium' | 'high' | 'urgent'`, optional, default `'medium'`). Allowed for all authenticated roles.
  - `category` (`'network' | 'hardware' | 'software' | 'access' | 'email' | 'other'`, optional, default `'other'`).
- **Response**: HTTP 201 Created with full `TicketRead` schema.
- **Requester Binding**: `requester_id` is always forced from `current_user.id` on backend.
- **Validation Errors (HTTP 422)**: Standardized by backend exception handler as `{"error": {"message": "body.<field>: <msg>; ..."}}`.

### POST /api/v1/triage/suggest (AI Triage Suggestions & Duplicate Detection)
- **Request Body (`TriageSuggestRequest`)**:
  - `title` (`string`, required): min 1, max 255 characters.
  - `description` (`string`, required): min 1 character.
- **Minimum Text Rule**: Backend requires at least 1 character; frontend enforces a 15-character minimum for `title.trim() + description.trim()` with ~600ms debounce before invoking suggestion.
- **Response Shape (`TriageSuggestResponse`)**:
  - `suggested_category` (`TicketCategory | null`): similarity-weighted vote over top $k=5$ resolved/closed tickets with cosine similarity $\ge 0.12$. Returns `null` if no tickets meet the threshold.
  - `suggested_priority` (`TicketPriority | null`): similarity-weighted vote over top $k=5$ neighbours (permanently labeled "low reliability" in UI).
  - `confidence` (`float`, 0.0 to 1.0): winning category weight divided by total weight of top candidates.
  - `evidence` (`SimilarTicket[]`): list of top similar resolved/closed tickets used for triage voting. Contains `id`, `title`, `status`, `category`, `priority`, and `similarity` (float).
  - `possible_duplicates` (`SimilarTicket[]`): active tickets (`open`, `in_progress`, `waiting_on_requester`) with cosine similarity $\ge 0.80$ (`AI_DUPLICATE_THRESHOLD`).
  - `embedder` (`string`): name of the active embedder backend (`"hashing-v2"`).
- **Privacy Enforcement**: The backend filters `evidence` and `possible_duplicates` at SQL/service level so that users with `requester` role only ever see their own tickets (`requester_id == current_user.id`).
- **Evaluation Metrics (from docs/AI_TRIAGE.md)**:
  - Dataset: 24 held-out test tickets from a synthetic 120-ticket dataset.
  - Category Accuracy: 58.33% vs 16.67% random chance (1 of 6).
  - Priority Accuracy: 37.50% vs 38.33% majority class baseline (does not beat baseline).
  - Method: Lexical n-gram feature hashing comparison against past tickets.


## Ticket detail

### Endpoints and Contract
- **Ticket Details**: `GET /api/v1/tickets/{id}`
  - Returns `TicketRead`: `id`, `title`, `description`, `status`, `priority`, `category`, `requester_id`, `assignee_id`, `requester_name`, `assignee_name`, `due_at`, `sla_paused_at`, `created_at`, `updated_at`, `is_overdue`.
  - Requesters can only access their own tickets (`requester_id == current_user.id`); unauthorized IDs return `404 Not Found` (never 403, preventing enumeration). Staff see all tickets.
- **Comments**:
  - `GET /api/v1/tickets/{id}/comments`: Requesters only receive public comments (`is_internal == false`). Staff receive all comments.
  - `POST /api/v1/tickets/{id}/comments`: Payload `{ body: string (1-2000 chars), is_internal?: boolean }`. Requesters cannot set `is_internal=true` (returns 403). Closed tickets reject comments with `409 Conflict`.
- **Status History Audit**: `GET /api/v1/tickets/{id}/history`
  - Returns list of `StatusHistoryRead`: `id`, `ticket_id`, `changed_by_id`, `from_status` (null for creation), `to_status`, `created_at` (ascending).
- **Status Transitions**: `PATCH /api/v1/tickets/{id}/status`
  - Payload `{ status: TicketStatus }`. Staff only (`agent`, `admin`).
  - Allowed transitions: `open -> in_progress`; `in_progress -> waiting_on_requester | resolved`; `waiting_on_requester -> in_progress`; `resolved -> closed | in_progress` (reopen); `closed -> none`.
  - Moving to `waiting_on_requester` freezes the SLA clock (`sla_paused_at`). Resuming to `in_progress` extends `due_at` by elapsed business minutes and unpauses. Invalid transitions return `409 Conflict`.
- **Assignment**: `PATCH /api/v1/tickets/{id}/assign`
  - Payload `{ assignee_id: number }`. Staff only. Assignee must be an active agent (422 if inactive or requester). Closed tickets return `409 Conflict`. Assigning an open ticket automatically transitions it to `in_progress`.
- **Similar Tickets**: `GET /api/v1/tickets/{id}/similar?limit=5`
  - Staff only (`agent`, `admin`). Requesters get `403 Forbidden`. Returns `[{ id, title, status, category, priority, similarity }]`.
- **User Roster & Author Resolution**:
  - `GET /api/v1/users` is restricted to admins only.
  - Comment and history schemas return `author_id` / `changed_by_id` as integers. The UI resolves names via a pure function `resolveActorName` matching against ticket `requester_id`, `assignee_id`, or `current_user.id`, falling back to `System` for null or `Staff member` for other IDs.
- **SLA Calculation**:
  - The API does not return remaining or elapsed business time. The web UI computes remaining business minutes, overdue duration, and elapsed window ratio client-side in `Asia/Kolkata` working hours (09:00–18:00, Mon–Fri, excluding holidays).
