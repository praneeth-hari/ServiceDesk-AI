import type { Holiday } from '../../api/holidays';

const MONTH_NAMES = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

const WEEKDAY_NAMES = [
  'Sunday',
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
];

/**
 * Parse a "YYYY-MM-DD" string into integer year, month (1-12), and day (1-31).
 * Never uses `new Date("YYYY-MM-DD")` to avoid UTC parsing timezone shifts.
 */
export function parseDateParts(dateStr: string): {
  year: number;
  month: number;
  day: number;
} {
  const parts = dateStr.split('-');
  const year = parseInt(parts[0], 10);
  const month = parseInt(parts[1], 10);
  const day = parseInt(parts[2], 10);
  return { year, month, day };
}

/**
 * Calculates the day of the week (0 = Sunday, 1 = Monday, ..., 6 = Saturday)
 * using Tomohiko Sakamoto's calendar algorithm. Pure arithmetic, zero timezone dependence.
 */
export function getWeekdayIndex(dateStr: string): number {
  const { year, month, day } = parseDateParts(dateStr);
  const t = [0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4];
  let y = year;
  if (month < 3) {
    y -= 1;
  }
  return (
    (y +
      Math.floor(y / 4) -
      Math.floor(y / 100) +
      Math.floor(y / 400) +
      t[month - 1] +
      day) %
    7
  );
}

/**
 * Returns full English weekday name (e.g. "Monday", "Saturday") for a "YYYY-MM-DD" date.
 */
export function getWeekdayName(dateStr: string): string {
  const idx = getWeekdayIndex(dateStr);
  return WEEKDAY_NAMES[idx];
}

/**
 * Returns true if the date falls on Saturday (6) or Sunday (0).
 */
export function isWeekend(dateStr: string): boolean {
  const idx = getWeekdayIndex(dateStr);
  return idx === 0 || idx === 6;
}

/**
 * Formats a "YYYY-MM-DD" string into "Jan 26, 2026" or "Oct 2, 2026" without Date constructor.
 * Day is not zero-padded.
 */
export function formatDateDisplay(dateStr: string): string {
  const { year, month, day } = parseDateParts(dateStr);
  const monthName = MONTH_NAMES[month - 1] || '';
  return `${monthName} ${day}, ${year}`;
}

/**
 * Filters holidays list by calendar year.
 */
export function filterHolidaysByYear(
  holidays: Holiday[],
  year: number
): Holiday[] {
  const prefix = `${year}-`;
  return holidays.filter((h) => h.holiday_date.startsWith(prefix));
}

/**
 * Sorts holidays chronologically ascending.
 */
export function sortHolidaysAsc(holidays: Holiday[]): Holiday[] {
  return [...holidays].sort((a, b) =>
    a.holiday_date.localeCompare(b.holiday_date)
  );
}
