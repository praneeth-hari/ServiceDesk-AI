# Operational Reports Feature Contract & Implementation Notes

## Backend Contract Findings (GET /api/v1/reports/*)

All endpoints are hosted under `/api/v1/reports` and are restricted to staff roles (`agent` and `admin`). Calls made by a `requester` return HTTP 403 Forbidden (`{"error": {"message": "You do not have permission to access this resource"}}`).

### Verified Endpoints & Schemas

1. **`GET /api/v1/reports/tickets-by-status`**
   - Returns: `list[TicketsByStatusItem]`
   - Fields: `status` (`'open' | 'in_progress' | 'waiting_on_requester' | 'resolved' | 'closed'`), `priority` (`'low' | 'medium' | 'high' | 'urgent'`), `count` (`number`).
   - Query Parameters: None.

2. **`GET /api/v1/reports/overdue`**
   - Returns: `list[OverdueTicketItem]`
   - Fields: `id` (`number`), `title` (`string`), `status` (`TicketStatus`), `priority` (`TicketPriority`), `due_at` (`string`, ISO 8601 UTC), `requester_id` (`number`), `requester_name` (`string`), `assignee_id` (`number | null`), `assignee_name` (`string | null`).
   - Query Parameters: None.

3. **`GET /api/v1/reports/resolution-time`**
   - Returns: `list[ResolutionTimeItem]`
   - Fields: `assignee_id` (`number`), `assignee_name` (`string`), `avg_resolution_hours` (`number`), `ticket_count` (`number`).
   - Query Parameters: None.

4. **`GET /api/v1/reports/agent-ranking`**
   - Returns: `list[AgentRankingItem]`
   - Fields: `rank` (`number`), `agent_id` (`number`), `agent_name` (`string`), `resolved_count` (`number`).
   - Query Parameters: None.

5. **`GET /api/v1/reports/daily-volume`**
   - Query Parameters: `days` (`number`, default `30`, constraints: 1 to 90).
   - Expected Contract: `list[DailyVolumeItem]`: `date` (`string`, "YYYY-MM-DD"), `ticket_count` (`number`).
   - **Observed Live Backend Difference**: The endpoint currently raises HTTP 500 (`fastapi.exceptions.ResponseValidationError`) on MySQL because `DATE(created_at)` produces Python `datetime.date` objects whereas `DailyVolumeItem` in `app/schemas/report.py` strictly specifies `date: str`. The frontend card handles this error gracefully with an isolated card error and a Retry button.

6. **`GET /api/v1/reports/sla-breach-rate`**
   - Returns: `list[SLABreachRateItem]`
   - Fields: `priority` (`TicketPriority`), `total_tickets` (`number`), `met_sla` (`number`), `breached_sla` (`number`), `breach_rate` (`number`, 0.0 to 100.0 with 1 decimal).
   - Query Parameters: None.

7. **`GET /api/v1/reports/resolution-time-by-category`**
   - Returns: `list[ResolutionTimeByCategoryItem]`
   - Fields: `category` (`TicketCategory | string`), `priority` (`TicketPriority`), `avg_resolution_hours` (`number`), `ticket_count` (`number`).
   - Query Parameters: None.

8. **`GET /api/v1/reports/agent-workload`**
   - Returns: `list[AgentWorkloadItem]`
   - Fields: `agent_id` (`number`), `agent_name` (`string`), `open_tickets` (`number`), `overdue_tickets` (`number`), `resolved_tickets` (`number`).
   - Query Parameters: None.

9. **`GET /api/v1/reports/tickets-by-category`**
   - Query Parameters: `breakdown_by_status` (`boolean`, default `false`).
   - Returns: `list[TicketsByCategoryItem]`
   - Fields: `category` (`TicketCategory | string`), `status` (`TicketStatus | null`, `null` when `breakdown_by_status=false`), `count` (`number`).

---

## Units & Calculation Notes

- **Elapsed Hours vs. Business Hours**:
  Resolution times (`avg_resolution_hours`) in reports measure elapsed wall-clock hours from ticket creation to first resolution (`created_at` to first `resolved` status history entry). They are not business hours.
- **Metric Types**:
  - Counts: Whole integers (`count`, `ticket_count`, `resolved_count`, `total_tickets`, `met_sla`, `breached_sla`, `open_tickets`, `overdue_tickets`, `resolved_tickets`, `rank`).
  - Durations: Hours formatted as decimal numbers rounded to 1 or 2 decimal places (`avg_resolution_hours`). Minutes are not used.
  - Rates: Percentages formatted with one decimal place (`breach_rate`, e.g. `25.0%`).
- **Timezone Grouping**:
  Dates in the database are stored as UTC timestamps. In `daily-volume`, grouping is performed directly via SQL `DATE(created_at)` on stored UTC timestamps without local timezone conversion.

