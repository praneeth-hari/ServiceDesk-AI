import { describe, it, expect } from 'vitest';
import {
  computeBusinessMinutesBetween,
  computeBusinessMinutesRemaining,
  buildTimelineWindow,
  mapTimeToPosition,
  formatDurationShort,
  toKolkataWallClock,
  fromKolkataWallClock,
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
});

