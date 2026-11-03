import { describe, it, expect } from 'vitest';
import {
  computeBusinessMinutesBetween,
  computeBusinessMinutesRemaining,
  buildTimelineWindow,
  mapTimeToPosition,
  formatDurationShort,
  formatSlaText,
  toKolkataWallClock,
  fromKolkataWallClock,
  parseToUtcDate,
} from '../businessTime';

describe('businessTime pure functions', () => {
  it('converts between Kolkata wall clock and UTC correctly', () => {
    // 2026-10-26 09:00:00 IST -> UTC is 2026-10-26 03:30:00 UTC
    const utcDate = fromKolkataWallClock(2026, 9, 26, 9, 0, 0); // month 9 is October (0-indexed)
    expect(utcDate.toISOString()).toBe('2026-10-26T03:30:00.000Z');

    const wallClock = toKolkataWallClock(utcDate);
    expect(wallClock.getUTCFullYear()).toBe(2026);
    expect(wallClock.getUTCMonth()).toBe(9);
    expect(wallClock.getUTCDate()).toBe(26);
    expect(wallClock.getUTCHours()).toBe(9);
    expect(wallClock.getUTCMinutes()).toBe(0);
  });

  it('normalizes naive ISO strings to UTC using parseToUtcDate', () => {
    // Naive ISO string without timezone indicator should be parsed as UTC
    const d1 = parseToUtcDate('2026-11-03T04:27:00');
    expect(d1.toISOString()).toBe('2026-11-03T04:27:00.000Z');

    // String with Z is parsed as UTC
    const d2 = parseToUtcDate('2026-11-03T04:27:00Z');
    expect(d2.toISOString()).toBe('2026-11-03T04:27:00.000Z');

    // Date object returned as a cloned Date
    const orig = new Date('2026-11-03T04:27:00.000Z');
    const d3 = parseToUtcDate(orig);
    expect(d3.getTime()).toBe(orig.getTime());
  });

  it('computes business minutes within the same business day', () => {
    // Monday 09:00 IST to Monday 12:30 IST -> 3.5 hours = 210 minutes
    const start = fromKolkataWallClock(2026, 9, 26, 9, 0, 0);
    const end = fromKolkataWallClock(2026, 9, 26, 12, 30, 0);

    const mins = computeBusinessMinutesBetween(start, end);
    expect(mins).toBe(210);
  });

  it('clamps to business hours (09:00 to 18:00)', () => {
    // Monday 08:00 IST (before start) to Monday 19:00 IST (after end)
    // Full business day = 9 hours = 540 minutes
    const start = fromKolkataWallClock(2026, 9, 26, 8, 0, 0);
    const end = fromKolkataWallClock(2026, 9, 26, 19, 0, 0);

    const mins = computeBusinessMinutesBetween(start, end);
    expect(mins).toBe(540);
  });

  it('skips weekends entirely', () => {
    // Saturday 10:00 IST to Sunday 16:00 IST -> 0 minutes
    const start = fromKolkataWallClock(2026, 9, 24, 10, 0, 0); // Saturday
    const end = fromKolkataWallClock(2026, 9, 25, 16, 0, 0); // Sunday

    const mins = computeBusinessMinutesBetween(start, end);
    expect(mins).toBe(0);
  });

  it('computes business minutes for a ticket spanning a weekend', () => {
    // Friday Oct 23, 17:00 IST to Monday Oct 26, 10:00 IST:
    // Friday: 17:00 to 18:00 = 60 mins
    // Sat & Sun: 0 mins
    // Monday: 09:00 to 10:00 = 60 mins
    // Total = 120 mins
    const start = fromKolkataWallClock(2026, 9, 23, 17, 0, 0);
    const end = fromKolkataWallClock(2026, 9, 26, 10, 0, 0);

    const mins = computeBusinessMinutesBetween(start, end);
    expect(mins).toBe(120);
  });

  it('computes remaining business minutes and negative when overdue', () => {
    const now = fromKolkataWallClock(2026, 9, 26, 11, 0, 0);
    const dueFuture = fromKolkataWallClock(2026, 9, 26, 13, 0, 0);
    const duePast = fromKolkataWallClock(2026, 9, 26, 10, 0, 0);

    // 2 hours in the future = 120 mins
    expect(computeBusinessMinutesRemaining(dueFuture, now)).toBe(120);
    // 1 hour in the past = -60 mins
    expect(computeBusinessMinutesRemaining(duePast, now)).toBe(-60);
  });

  it('formats durations cleanly', () => {
    expect(formatDurationShort(45)).toBe('45m');
    expect(formatDurationShort(120)).toBe('2h');
    expect(formatDurationShort(270)).toBe('4h 30m');
    expect(formatDurationShort(-90)).toBe('1h 30m');
  });

  it('builds timeline window with business day columns and weekend bands', () => {
    const anchor = fromKolkataWallClock(2026, 9, 26, 12, 0, 0); // Monday
    const window = buildTimelineWindow(anchor, 7, 100, 30);

    expect(window.columns.length).toBeGreaterThan(0);
    expect(window.totalWidth).toBeGreaterThan(0);

    const weekendCols = window.columns.filter((c) => c.type === 'weekend');
    const dayCols = window.columns.filter((c) => c.type === 'day');

    expect(weekendCols.length).toBeGreaterThanOrEqual(1);
    expect(dayCols.length).toBe(7);
  });

  it('clips positions left and right properly', () => {
    const anchor = fromKolkataWallClock(2026, 9, 26, 12, 0, 0);
    const window = buildTimelineWindow(anchor, 7, 100, 30);

    const wayPast = new Date('2020-01-01T00:00:00Z');
    const wayFuture = new Date('2030-01-01T00:00:00Z');

    const leftPos = mapTimeToPosition(wayPast, window);
    expect(leftPos.isClippedLeft).toBe(true);
    expect(leftPos.x).toBe(0);

    const rightPos = mapTimeToPosition(wayFuture, window);
    expect(rightPos.isClippedRight).toBe(true);
    expect(rightPos.x).toBe(window.totalWidth);

    const insidePos = mapTimeToPosition(anchor, window);
    expect(insidePos.isClippedLeft).toBe(false);
    expect(insidePos.isClippedRight).toBe(false);
    expect(insidePos.x).toBeGreaterThan(0);
    expect(insidePos.x).toBeLessThan(window.totalWidth);
  });
describe('Breach duration and Time Left calculations (IST business hours 09:00 - 18:00)', () => {
    // 1. Same-day due 09:57 IST, now 17:57 IST -> exactly 8h 00m elapsed
    it('computes breached duration for due 09:57 IST and now 17:57 IST on the same day (8h 00m)', () => {
      // 09:57 IST = 04:27 UTC
      const dueIsoZ = '2026-11-03T04:27:00Z';
      const nowIsoZ = '2026-11-03T12:27:00Z'; // 17:57 IST = 12:27 UTC

      const remZ = computeBusinessMinutesRemaining(dueIsoZ, nowIsoZ);
      expect(remZ).toBe(-480);
      expect(formatDurationShort(remZ)).toBe('8h');
      expect(formatSlaText(remZ, 'open', true, false)).toBe('breached 8h');

      // Test with naive ISO string (as returned from SQLite/DB serialization without Z)
      const dueNaive = '2026-11-03T04:27:00';
      const nowNaive = '2026-11-03T12:27:00';
      const remNaive = computeBusinessMinutesRemaining(dueNaive, nowNaive);
      expect(remNaive).toBe(-480);
      expect(formatDurationShort(remNaive)).toBe('8h');
      expect(formatSlaText(remNaive, 'open', true, false)).toBe('breached 8h');

      // Test with Date objects
      const dueObj = fromKolkataWallClock(2026, 10, 3, 9, 57, 0);
      const nowObj = fromKolkataWallClock(2026, 10, 3, 17, 57, 0);
      expect(computeBusinessMinutesRemaining(dueObj, nowObj)).toBe(-480);
    });

    // 2. Due late in the day and now next morning
    it('computes breached duration when due late in the day and now is next morning', () => {
      // Due Monday Nov 2 at 17:30 IST (30m left until 18:00 close)
      // Now Tuesday Nov 3 at 09:30 IST (30m into Tuesday workday)
      // Total elapsed overdue business minutes = 30 + 30 = 60 mins (1h)
      const due = fromKolkataWallClock(2026, 10, 2, 17, 30, 0);
      const now = fromKolkataWallClock(2026, 10, 3, 9, 30, 0);

      const rem = computeBusinessMinutesRemaining(due, now);
      expect(rem).toBe(-60);
      expect(formatDurationShort(rem)).toBe('1h');
      expect(formatSlaText(rem, 'in_progress', true, false)).toBe('breached 1h');
    });

    // 3. Across a weekend
    it('computes breached duration spanning a weekend', () => {
      // Due Friday Oct 30 at 17:00 IST (60m left until 18:00 Friday close)
      // Now Monday Nov 2 at 10:00 IST (60m into Monday workday, Sat/Sun 0m)
      // Total overdue = 60 + 60 = 120 mins (2h)
      const due = fromKolkataWallClock(2026, 9, 30, 17, 0, 0);
      const now = fromKolkataWallClock(2026, 10, 2, 10, 0, 0);

      const rem = computeBusinessMinutesRemaining(due, now);
      expect(rem).toBe(-120);
      expect(formatDurationShort(rem)).toBe('2h');
      expect(formatSlaText(rem, 'open', true, false)).toBe('breached 2h');
    });

    // 4. Due exactly on the hour
    it('computes breached duration when due exactly on the hour', () => {
      // Due Tuesday Nov 3 at 10:00 IST, now Tuesday Nov 3 at 14:00 IST (4h overdue = 240 mins)
      const due = fromKolkataWallClock(2026, 10, 3, 10, 0, 0);
      const now = fromKolkataWallClock(2026, 10, 3, 14, 0, 0);

      const rem = computeBusinessMinutesRemaining(due, now);
      expect(rem).toBe(-240);
      expect(formatDurationShort(rem)).toBe('4h');
      expect(formatSlaText(rem, 'open', true, false)).toBe('breached 4h');
    });

    // 5. Same cases for "time left" before due time
    it('computes time left before due time for all corresponding cases', () => {
      // Case A: now 09:57 IST, due 17:57 IST same day -> 8h left (480 mins)
      const nowA = fromKolkataWallClock(2026, 10, 3, 9, 57, 0);
      const dueA = fromKolkataWallClock(2026, 10, 3, 17, 57, 0);
      const remA = computeBusinessMinutesRemaining(dueA, nowA);
      expect(remA).toBe(480);
      expect(formatDurationShort(remA)).toBe('8h');
      expect(formatSlaText(remA, 'open', false, false)).toBe('8h left');

      // Also verify with naive strings for Case A
      const remANaive = computeBusinessMinutesRemaining('2026-11-03T12:27:00', '2026-11-03T04:27:00');
      expect(remANaive).toBe(480);

      // Case B: now Monday 17:30 IST, due Tuesday 09:30 IST -> 1h left (60 mins)
      const nowB = fromKolkataWallClock(2026, 10, 2, 17, 30, 0);
      const dueB = fromKolkataWallClock(2026, 10, 3, 9, 30, 0);
      const remB = computeBusinessMinutesRemaining(dueB, nowB);
      expect(remB).toBe(60);
      expect(formatDurationShort(remB)).toBe('1h');
      expect(formatSlaText(remB, 'open', false, false)).toBe('1h left');

      // Case C: now Friday 17:00 IST, due Monday 10:00 IST -> 2h left (120 mins)
      const nowC = fromKolkataWallClock(2026, 9, 30, 17, 0, 0);
      const dueC = fromKolkataWallClock(2026, 10, 2, 10, 0, 0);
      const remC = computeBusinessMinutesRemaining(dueC, nowC);
      expect(remC).toBe(120);
      expect(formatDurationShort(remC)).toBe('2h');
      expect(formatSlaText(remC, 'open', false, false)).toBe('2h left');

      // Case D: now Tuesday 10:00 IST, due Tuesday 14:00 IST -> 4h left (240 mins)
      const nowD = fromKolkataWallClock(2026, 10, 3, 10, 0, 0);
      const dueD = fromKolkataWallClock(2026, 10, 3, 14, 0, 0);
      const remD = computeBusinessMinutesRemaining(dueD, nowD);
      expect(remD).toBe(240);
      expect(formatDurationShort(remD)).toBe('4h');
      expect(formatSlaText(remD, 'open', false, false)).toBe('4h left');
    });
  });
});
