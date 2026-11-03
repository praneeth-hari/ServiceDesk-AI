import { apiFetch } from './client';

export interface Holiday {
  id: number;
  holiday_date: string; // YYYY-MM-DD
  name: string;
  created_at: string;
}

export interface HolidayCreate {
  holiday_date: string; // YYYY-MM-DD
  name: string;
}

export interface HolidayUpdate {
  holiday_date?: string; // YYYY-MM-DD
  name?: string;
}

/**
 * List official public holidays ordered chronologically.
 * Supports optional calendar year filtering on the server.
 */
export async function getHolidays(year?: number): Promise<Holiday[]> {
  const query = year !== undefined ? `?year=${year}` : '';
  return apiFetch<Holiday[]>(`/holidays${query}`);
}

/**
 * Create a new public holiday (Admin only).
 */
export async function createHoliday(data: HolidayCreate): Promise<Holiday> {
  return apiFetch<Holiday>('/holidays', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * Delete a holiday by ID (Admin only).
 */
export async function deleteHoliday(id: number): Promise<void> {
  return apiFetch<void>(`/holidays/${id}`, {
    method: 'DELETE',
  });
}

/**
 * Update an existing holiday (Admin only).
 */
export async function updateHoliday(
  id: number,
  data: HolidayUpdate
): Promise<Holiday> {
  return apiFetch<Holiday>(`/holidays/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}
