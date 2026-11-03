import { describe, it, expect } from 'vitest';
import {
  parseDateParts,
  getWeekdayName,
  isWeekend,
  formatDateDisplay,
  filterHolidaysByYear,
  sortHolidaysAsc,
} from '../holidayUtils';
import type { Holiday } from '../../../api/holidays';

describe('holidayUtils', () => {
  describe('parseDateParts', () => {
    it('parses YYYY-MM-DD correctly without Date constructor', () => {
      expect(parseDateParts('2026-01-01')).toEqual({ year: 2026, month: 1, day: 1 });
      expect(parseDateParts('2026-12-31')).toEqual({ year: 2026, month: 12, day: 31 });
    });
  });

  describe('getWeekdayName and year boundaries', () => {
    it('accurately computes weekdays near year boundaries in 2026', () => {
      // 2026-01-01 is Thursday
      expect(getWeekdayName('2026-01-01')).toBe('Thursday');

      // 2026-12-31 is Thursday
      expect(getWeekdayName('2026-12-31')).toBe('Thursday');

      // 2026-01-26 is Monday (Republic Day)
      expect(getWeekdayName('2026-01-26')).toBe('Monday');

      // 2026-08-15 is Saturday (Independence Day)
      expect(getWeekdayName('2026-08-15')).toBe('Saturday');

      // 2026-10-02 is Friday (Gandhi Jayanti)
      expect(getWeekdayName('2026-10-02')).toBe('Friday');
    });

    it('accurately computes leap year days', () => {
      // 2024 was leap year: Feb 29, 2024 was Thursday
      expect(getWeekdayName('2024-02-29')).toBe('Thursday');
      // 2024-01-01 was Monday
      expect(getWeekdayName('2024-01-01')).toBe('Monday');
    });
  });

  describe('isWeekend', () => {
    it('returns true for Saturday and Sunday dates', () => {
      expect(isWeekend('2026-08-15')).toBe(true); // Saturday
      expect(isWeekend('2026-08-16')).toBe(true); // Sunday
    });

    it('returns false for Monday through Friday dates', () => {
      expect(isWeekend('2026-01-26')).toBe(false); // Monday
      expect(isWeekend('2026-01-01')).toBe(false); // Thursday
      expect(isWeekend('2026-10-02')).toBe(false); // Friday
    });
  });

  describe('formatDateDisplay', () => {
    it('formats date cleanly into Month Day, Year without zero-padded day', () => {
      expect(formatDateDisplay('2026-01-26')).toBe('Jan 26, 2026');
      expect(formatDateDisplay('2026-08-15')).toBe('Aug 15, 2026');
      expect(formatDateDisplay('2026-10-02')).toBe('Oct 2, 2026');
      expect(formatDateDisplay('2026-01-05')).toBe('Jan 5, 2026');
      expect(formatDateDisplay('2026-12-31')).toBe('Dec 31, 2026');
    });
  });

  describe('filterHolidaysByYear', () => {
    const list: Holiday[] = [
      { id: 1, holiday_date: '2025-12-25', name: 'Christmas 2025', created_at: '' },
      { id: 2, holiday_date: '2026-01-26', name: 'Republic Day', created_at: '' },
      { id: 3, holiday_date: '2026-08-15', name: 'Independence Day', created_at: '' },
      { id: 4, holiday_date: '2027-01-01', name: 'New Year 2027', created_at: '' },
    ];

    it('filters holidays matching the given year', () => {
      const h2026 = filterHolidaysByYear(list, 2026);
      expect(h2026).toHaveLength(2);
      expect(h2026.map((h) => h.holiday_date)).toEqual(['2026-01-26', '2026-08-15']);

      const h2025 = filterHolidaysByYear(list, 2025);
      expect(h2025).toHaveLength(1);
      expect(h2025[0].name).toBe('Christmas 2025');

      const h2028 = filterHolidaysByYear(list, 2028);
      expect(h2028).toHaveLength(0);
    });
  });

  describe('sortHolidaysAsc', () => {
    it('sorts holidays chronologically ascending', () => {
      const unsorted: Holiday[] = [
        { id: 1, holiday_date: '2026-12-25', name: 'Christmas', created_at: '' },
        { id: 2, holiday_date: '2026-01-26', name: 'Republic Day', created_at: '' },
        { id: 3, holiday_date: '2026-08-15', name: 'Independence Day', created_at: '' },
      ];

      const sorted = sortHolidaysAsc(unsorted);
      expect(sorted.map((h) => h.holiday_date)).toEqual([
        '2026-01-26',
        '2026-08-15',
        '2026-12-25',
      ]);
    });
  });
});
