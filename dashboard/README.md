# HelpDesk Streamlit Dashboard

A modern, interactive management portal and analytics dashboard for the HelpDesk API built with Streamlit.

---

## Features

- **Authentication & Registration**: Clean tabbed login and registration interface storing JWT access tokens securely in memory (`st.session_state`).
- **Ticket Management (`Tickets`)**:
  - Filter by Status, Priority, Category (`network`, `hardware`, `software`, `access`, `email`, `other`), keyword search (`q`), and Overdue status.
  - Column layout displaying ID, Title, Category, Status, Priority, Assignee, Due date, and a quick "View" action button.
  - Full server-side pagination ("Page X of Y", "Showing a–b of N tickets") with automatic page-1 reset on filter adjustments.
  - Due dates highlighted in red with overdue indicators.
  - All timestamps automatically converted and formatted in the viewer's local timezone.
  - Paused tickets clearly display "SLA paused" in purple and are never flagged as overdue while paused.
  - Requester isolation enforced by backend API (requesters only see their own tickets).
- **Ticket Detail & Collaboration (`Ticket Detail`)**:
  - Status badges (including purple `WAITING ON REQUESTER`), priority, and category badges; SLA due dates; requester and assignee metadata.
  - Paused SLA banner alerting staff that the clock is frozen, with current due date caption.
  - Contextual status transition action buttons ("Pause SLA", "Resume work", "Resolve ticket", "Close ticket", "Reopen ticket", "Start work").
  - Category updates for ticket owners (while `open`) and staff (agents/admins anytime).
  - Comment stream with internal notes highlighted and labelled `[Internal]` for staff.
  - Ticket lifecycle status transitions with conflict handling (409 validation).
  - Agent assignment dropdown (with manual agent ID input fallback).
  - Status audit history timeline with local timezone timestamps.
- **AI Triage & Duplicate Detection (`New ticket`)**:
  - **Advisory Category & Priority Suggestions**: Users can click **🤖 Suggest category & priority** after typing a title or description. An AI suggestion card displays the recommended category badge, a confidence progress meter, and an expandable list of matching historical resolved tickets with similarity percentages.
  - **Advice Only**: Suggestions never mutate tickets automatically. Users choose whether to click **Apply category** or **Apply priority** to pre-fill form fields, and can override them at any time before clicking **Submit Ticket**.
  - **Priority-Hint Caveat**: Priority is presented as an advisory hint (*"Priority hint: {level} (low reliability, check it yourself)"*) because baseline priority estimation accuracy reflects dominant class distributions rather than strong predictive signal.
  - **Duplicate Detection**: Active tickets with high text similarity trigger a **⚠️ Possible duplicate** alert showing matched ticket ID, status, and similarity percent, with an **Open #id** direct link to view the ticket.
  - **Graceful Fallback**: If no confident match is found, an informational banner advises the user to select the category manually. API or network errors show a warning and never block ticket creation.
  - **Similar Tickets for Staff**: On the **Ticket Detail** page, agents and administrators have a **🔍 Similar Tickets** section ranked by text similarity to past tickets, allowing staff to quickly inspect and reuse verified fixes from resolved incidents. Requesters cannot see this section.
- **Holidays Management (`Holidays`)** *(Agent and Admin only)*:
  - Overview of official organizational holidays skipping the business-hours SLA clock.
  - Year filter and computed day-of-week display.
  - Admin controls for registering new holidays with duplicate date conflict protection (409 error handling) and holiday deletion.
- **Operational Analytics & KPI Reporting (`Reports`)** *(Agent and Admin only)*:
  - Real-time KPI metric cards (Open, In Progress, Overdue, SLA Breach Rate %, and Average Resolution Hours).
  - Status distribution bar chart and Tickets by Category bar chart.
  - SLA breach rate by priority bar chart (comparing met vs breached tickets).
  - Average resolution time by category bar chart.
  - Agent rankings with tie handling (`RANK()` window function) and comprehensive Agent Workload table (open work, overdue tickets, and resolved counts).
  - Tickets created per day line chart with adjustable window (7–90 days).
  - Division-by-zero protection and friendly empty-state notifications.

> **Note on Timezones**: All timestamps (ticket creation, SLA due dates, comments, and status audit transitions) are stored and transmitted in UTC by the backend API and converted to the viewer's local machine timezone for display.

---

## Prerequisites & Installation

Ensure you have a Python 3.11+ virtual environment activated.

Install dashboard dependencies:

```powershell
pip install -r dashboard/requirements.txt
```

---

## Configuration

The dashboard communicates with the backend API over HTTP. Configure the API endpoint using the environment variable:

| Environment Variable | Description | Default |
| :--- | :--- | :--- |
| `HELPDESK_API_URL` | Base URL of the Helpdesk REST API | `http://localhost:8000/api/v1` |

---

## Running the Application

### 1. Start the HelpDesk API Backend

From the project root in Windows PowerShell:

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

### 2. Start the Streamlit Dashboard

In a separate Windows PowerShell terminal:

```powershell
.venv\Scripts\Activate.ps1
python -m streamlit run dashboard/app.py
```

The dashboard will open automatically in your browser at `http://localhost:8501`.

---

## Demo Accounts Setup

You can test different role-based views (Requester, Agent, Admin) with the following steps:

### 1. Admin Account

Generate an initial administrator account using the management script:

```powershell
python -m app.scripts.create_admin --email admin@example.com --password AdminPassword123! --name "System Admin"
```

### 2. Requester Account

Requesters can self-register directly through the dashboard UI:

1. Open `http://localhost:8501`.
2. Click the **Register** tab.
3. Fill in name, email (e.g. `requester@example.com`), and password (min 8 characters).
4. Click **Create Account** and log in.

### 3. Agent Account

Create an agent account directly via an authenticated admin session or database:

- An Admin can promote or create an agent, or you can register an account and update the `role` column to `'agent'` in the `users` table:

```sql
UPDATE users SET role = 'agent' WHERE email = 'agent@example.com';
```

---

## License

This project is licensed under the [MIT License](../LICENSE).
