# Holidays Feature (web/src/features/holidays)

The Holidays feature provides an administrative control center for registering and maintaining organizational public holidays.

## Architecture

- **`HolidaysPage.tsx`**: Main administrative dashboard wrapped in `RoleRoute` (`adminOnly`). Agents and requesters navigating directly are redirected to `/tickets`. Features responsive layouts (table on desktop, stacked card/row on mobile < 390px).
- **`holidayUtils.ts`**: Pure functions for date parsing, Sakamoto weekday calculation, weekend detection, year filtering, and chronological sorting.
- **`components/DeleteHolidayModal.tsx`**: Accessible confirmation modal rendered via React portal directly into `document.body` with focus trapping and `Escape` key close.
- **`components/SlaNoteCard.tsx`**: Context card explaining the impact of observed holidays on business-hour SLA calculations.
- **`web/src/api/holidays.ts`**: Dedicated typed client using `apiFetch`.

## Verified API Contract

All endpoints are hosted under `/api/v1/holidays`:
- `GET /api/v1/holidays?year=<int>`: Chronological listing of official holidays. Allowed roles: `admin`, `agent`. Requesters receive 403 Forbidden.
- `POST /api/v1/holidays`: Create a new holiday (`{ holiday_date: "YYYY-MM-DD", name: string }`). Allowed roles: `admin` only. Duplicate dates return 409 Conflict.
- `PATCH /api/v1/holidays/:id`: Update an existing holiday (`{ holiday_date?: "YYYY-MM-DD", name?: string }`). Allowed roles: `admin` only. Returns 404 if not found, 409 if the updated date is already taken by another holiday. Non-conflicting / same-date updates succeed.
- `DELETE /api/v1/holidays/:id`: Delete a holiday by ID. Allowed roles: `admin` only.
