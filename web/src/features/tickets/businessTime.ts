import {
  WORK_TZ_OFFSET_MINUTES,
  WORK_DAY_START_HOUR,
  WORK_DAY_END_HOUR,
  WORK_DAYS,
  DEFAULT_DAY_WIDTH,
  DEFAULT_WEEKEND_WIDTH,
} from './constants';

export interface TimelineColumn {
  type: 'day' | 'weekend';
  dateStr: string; // YYYY-MM-DD in Kolkata wall clock
  label: string; // e.g. "Mon, Oct 26" or "Weekend"
  subLabel?: string;
  dayOfWeek: number; // 0=Sun, 1=Mon, ..., 6=Sat
  x: number;
  width: number;
  startUtcMs: number;
  endUtcMs: number;
}

export interface TimelineWindow {
  columns: TimelineColumn[];
  totalWidth: number;
  startUtcMs: number;
  endUtcMs: number;
}

/**
 * Returns a Date object where getUTC* methods correspond to Asia/Kolkata local wall-clock components.
 */
export function toKolkataWallClock(input: Date | string | number): Date {
  let d: Date;
  if (typeof input === 'string') {
    let str = input.trim();
    if (/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(str)) {
      str = str.replace(' ', 'T') + 'Z';
    }
    d = new Date(str);
  } else if (typeof input === 'object') {
    d = input;
  } else {
    d = new Date(input);
  }
  const utcMs = d.getTime();
  return new Date(utcMs + WORK_TZ_OFFSET_MINUTES * 60 * 1000);
}

/**
 * Converts local Asia/Kolkata wall-clock components back to a UTC Date.
 */
export function fromKolkataWallClock(
  year: number,
  month: number, // 0-indexed
  day: number,
  hour = 0,
  minute = 0,
  second = 0
): Date {
  const utcMs = Date.UTC(year, month, day, hour, minute, second);
  return new Date(utcMs - WORK_TZ_OFFSET_MINUTES * 60 * 1000);
}

export function isWorkDay(kolkataDate: Date): boolean {
  const day = kolkataDate.getUTCDay();
  return WORK_DAYS.includes(day);
}

/**
 * Calculates total business minutes elapsed between start and end.
 * Working hours are 09:00 - 18:00 (Asia/Kolkata), Monday through Friday.
 */
export function computeBusinessMinutesBetween(
  startInput: Date | string | number,
  endInput: Date | string | number
): number {
  const start = typeof startInput === 'object' ? startInput : new Date(startInput);
  const end = typeof endInput === 'object' ? endInput : new Date(endInput);

  if (end.getTime() <= start.getTime()) {
    return 0;
  }

  const startKolkata = toKolkataWallClock(start);
  const endKolkata = toKolkataWallClock(end);

  const startYear = startKolkata.getUTCFullYear();
  const startMonth = startKolkata.getUTCMonth();
  const startDate = startKolkata.getUTCDate();

  const endYear = endKolkata.getUTCFullYear();
  const endMonth = endKolkata.getUTCMonth();
  const endDate = endKolkata.getUTCDate();

  const dayStartMins = WORK_DAY_START_HOUR * 60; // 540
  const dayEndMins = WORK_DAY_END_HOUR * 60; // 1080

  let totalMinutes = 0;
  let curKolkataDay = new Date(Date.UTC(startYear, startMonth, startDate));
  const endKolkataDay = new Date(Date.UTC(endYear, endMonth, endDate));

  while (curKolkataDay.getTime() <= endKolkataDay.getTime()) {
    if (isWorkDay(curKolkataDay)) {
      const isStartDay = curKolkataDay.getTime() === Date.UTC(startYear, startMonth, startDate);
      const isEndDay = curKolkataDay.getTime() === Date.UTC(endYear, endMonth, endDate);

      let effectiveStart = dayStartMins;
      let effectiveEnd = dayEndMins;

      if (isStartDay) {
        const startMins = startKolkata.getUTCHours() * 60 + startKolkata.getUTCMinutes();
        effectiveStart = Math.max(dayStartMins, startMins);
      }

      if (isEndDay) {
        const endMins = endKolkata.getUTCHours() * 60 + endKolkata.getUTCMinutes();
        effectiveEnd = Math.min(dayEndMins, endMins);
      }

      if (effectiveEnd > effectiveStart) {
        totalMinutes += effectiveEnd - effectiveStart;
      }
    }

    curKolkataDay = new Date(curKolkataDay.getTime() + 24 * 60 * 60 * 1000);
  }

  return totalMinutes;
}

/**
 * Computes remaining business minutes between now and dueAt.
 * If dueAt is in the past, returns a negative value representing elapsed overdue business minutes.
 */
export function computeBusinessMinutesRemaining(
  dueAtInput: Date | string | number | null | undefined,
  nowInput: Date | string | number = new Date()
): number {
  if (!dueAtInput) return 0;
  const due = typeof dueAtInput === 'object' ? dueAtInput : new Date(dueAtInput);
  const now = typeof nowInput === 'object' ? nowInput : new Date(nowInput);

  if (now.getTime() <= due.getTime()) {
    return computeBusinessMinutesBetween(now, due);
  }
  // Overdue: negative business minutes
  return -computeBusinessMinutesBetween(due, now);
}

/**
 * Format hours & minutes nicely: e.g. 4h 30m or 45m
 */
export function formatDurationShort(minutes: number): string {
  const abs = Math.abs(minutes);
  const h = Math.floor(abs / 60);
  const m = abs % 60;
  if (h === 0) return `${m}m`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

export function formatDurationLong(minutes: number): string {
  const abs = Math.abs(minutes);
  const h = Math.floor(abs / 60);
  const m = abs % 60;
  if (h === 0) return `${m} minute${m === 1 ? '' : 's'}`;
  if (m === 0) return `${h} hour${h === 1 ? '' : 's'}`;
  return `${h} hour${h === 1 ? '' : 's'} ${m} minute${m === 1 ? '' : 's'}`;
}

export function formatKolkataDateTime(input: Date | string | number | null | undefined): string {
  if (!input) return '—';
  const kolkata = toKolkataWallClock(input);
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const month = months[kolkata.getUTCMonth()];
  const day = kolkata.getUTCDate();
  const year = kolkata.getUTCFullYear();
  const hours = String(kolkata.getUTCHours()).padStart(2, '0');
  const minutes = String(kolkata.getUTCMinutes()).padStart(2, '0');
  return `${month} ${day}, ${year} ${hours}:${minutes} IST`;
}

export function formatKolkataShortDate(input: Date | string | number | null | undefined): string {
  if (!input) return '—';
  const kolkata = toKolkataWallClock(input);
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const month = months[kolkata.getUTCMonth()];
  const day = kolkata.getUTCDate();
  return `${month} ${day}`;
}

export function formatSlaText(
  minutesRemaining: number,
  status: string,
  isOverdue: boolean,
  isPaused: boolean
): string {
  if (status === 'resolved' || status === 'closed') {
    return 'met';
  }
  if (isPaused || status === 'waiting_on_requester') {
    return 'clock paused';
  }
  if (isOverdue || minutesRemaining < 0) {
    return `breached ${formatDurationShort(minutesRemaining)}`;
  }
  return `${formatDurationShort(minutesRemaining)} left`;
}

/**
 * Builds a continuous timeline window consisting of `numBusinessDays` business days,
 * with weekends collapsing into narrow hatched bands.
 */
export function buildTimelineWindow(
  anchorDateInput: Date | string | number = new Date(),
  numBusinessDays = 7,
  dayWidth = DEFAULT_DAY_WIDTH,
  weekendWidth = DEFAULT_WEEKEND_WIDTH
): TimelineWindow {
  const anchor = typeof anchorDateInput === 'object' ? anchorDateInput : new Date(anchorDateInput);
  const anchorKolkata = toKolkataWallClock(anchor);

  // Find the start date for the 7 business days window:
  // Align to beginning of anchor's business day (or previous Friday if weekend)
  let curDay = new Date(Date.UTC(
    anchorKolkata.getUTCFullYear(),
    anchorKolkata.getUTCMonth(),
    anchorKolkata.getUTCDate()
  ));

  // If weekend, roll back to Friday
  while (!isWorkDay(curDay)) {
    curDay = new Date(curDay.getTime() - 24 * 60 * 60 * 1000);
  }

  // Go back ~1-2 business days so anchor is comfortably inside the view
  let stepsBack = 1;
  while (stepsBack > 0) {
    const prev = new Date(curDay.getTime() - 24 * 60 * 60 * 1000);
    if (isWorkDay(prev)) {
      stepsBack--;
    }
    curDay = prev;
  }

  // Ensure start is on a work day
  while (!isWorkDay(curDay)) {
    curDay = new Date(curDay.getTime() + 24 * 60 * 60 * 1000);
  }

  const columns: TimelineColumn[] = [];
  let businessDaysCollected = 0;
  let currentX = 0;

  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

  while (businessDaysCollected < numBusinessDays) {
    const dayOfWeek = curDay.getUTCDay();

    if (dayOfWeek === 6) {
      // Saturday: start a combined weekend band (Sat + Sun)
      const satStartUtc = fromKolkataWallClock(
        curDay.getUTCFullYear(),
        curDay.getUTCMonth(),
        curDay.getUTCDate(),
        0, 0, 0
      );
      const sunEndUtc = fromKolkataWallClock(
        curDay.getUTCFullYear(),
        curDay.getUTCMonth(),
        curDay.getUTCDate() + 1,
        24, 0, 0
      );

      columns.push({
        type: 'weekend',
        dateStr: `${curDay.getUTCFullYear()}-${String(curDay.getUTCMonth() + 1).padStart(2, '0')}-${String(curDay.getUTCDate()).padStart(2, '0')}`,
        label: 'Weekend',
        subLabel: 'SLA paused',
        dayOfWeek: 6,
        x: currentX,
        width: weekendWidth,
        startUtcMs: satStartUtc.getTime(),
        endUtcMs: sunEndUtc.getTime(),
      });

      currentX += weekendWidth;
      // Skip ahead to Monday
      curDay = new Date(curDay.getTime() + 2 * 24 * 60 * 60 * 1000);
      continue;
    }

    if (dayOfWeek === 0) {
      // Standalone Sunday (rare edge case if window starts on Sun)
      const sunStartUtc = fromKolkataWallClock(
        curDay.getUTCFullYear(),
        curDay.getUTCMonth(),
        curDay.getUTCDate(),
        0, 0, 0
      );
      const sunEndUtc = fromKolkataWallClock(
        curDay.getUTCFullYear(),
        curDay.getUTCMonth(),
        curDay.getUTCDate(),
        24, 0, 0
      );

      columns.push({
        type: 'weekend',
        dateStr: `${curDay.getUTCFullYear()}-${String(curDay.getUTCMonth() + 1).padStart(2, '0')}-${String(curDay.getUTCDate()).padStart(2, '0')}`,
        label: 'Sunday',
        subLabel: 'SLA paused',
        dayOfWeek: 0,
        x: currentX,
        width: weekendWidth,
        startUtcMs: sunStartUtc.getTime(),
        endUtcMs: sunEndUtc.getTime(),
      });

      currentX += weekendWidth;
      curDay = new Date(curDay.getTime() + 24 * 60 * 60 * 1000);
      continue;
    }

    // Normal business day (Mon - Fri)
    const workStartUtc = fromKolkataWallClock(
      curDay.getUTCFullYear(),
      curDay.getUTCMonth(),
      curDay.getUTCDate(),
      WORK_DAY_START_HOUR,
      0,
      0
    );
    const workEndUtc = fromKolkataWallClock(
      curDay.getUTCFullYear(),
      curDay.getUTCMonth(),
      curDay.getUTCDate(),
      WORK_DAY_END_HOUR,
      0,
      0
    );

    const dateStr = `${curDay.getUTCFullYear()}-${String(curDay.getUTCMonth() + 1).padStart(2, '0')}-${String(curDay.getUTCDate()).padStart(2, '0')}`;
    const label = `${dayNames[dayOfWeek]}, ${monthNames[curDay.getUTCMonth()]} ${curDay.getUTCDate()}`;

    columns.push({
      type: 'day',
      dateStr,
      label,
      subLabel: '09:00 - 18:00',
      dayOfWeek,
      x: currentX,
      width: dayWidth,
      startUtcMs: workStartUtc.getTime(),
      endUtcMs: workEndUtc.getTime(),
    });

    currentX += dayWidth;
    businessDaysCollected++;
    curDay = new Date(curDay.getTime() + 24 * 60 * 60 * 1000);
  }

  const startUtcMs = columns[0].startUtcMs;
  const endUtcMs = columns[columns.length - 1].endUtcMs;

  return {
    columns,
    totalWidth: currentX,
    startUtcMs,
    endUtcMs,
  };
}

/**
 * Maps a UTC timestamp to an X position on the business-hours timeline.
 */
export function mapTimeToPosition(
  timeInput: Date | string | number | null | undefined,
  window: TimelineWindow
): { x: number; isClippedLeft: boolean; isClippedRight: boolean } {
  if (!timeInput) {
    return { x: 0, isClippedLeft: false, isClippedRight: false };
  }
  const d = typeof timeInput === 'object' ? timeInput : new Date(timeInput);
  const timeMs = d.getTime();

  if (timeMs < window.startUtcMs) {
    return { x: 0, isClippedLeft: true, isClippedRight: false };
  }
  if (timeMs > window.endUtcMs) {
    return { x: window.totalWidth, isClippedLeft: false, isClippedRight: true };
  }

  // Check each column
  for (let i = 0; i < window.columns.length; i++) {
    const col = window.columns[i];

    if (timeMs >= col.startUtcMs && timeMs <= col.endUtcMs) {
      const span = col.endUtcMs - col.startUtcMs;
      const progress = span > 0 ? (timeMs - col.startUtcMs) / span : 0;
      return {
        x: col.x + col.width * Math.max(0, Math.min(1, progress)),
        isClippedLeft: false,
        isClippedRight: false,
      };
    }

    // Between business day end and next day start (overnight)
    if (i < window.columns.length - 1) {
      const nextCol = window.columns[i + 1];
      if (timeMs > col.endUtcMs && timeMs < nextCol.startUtcMs) {
        // Clamp to end of current day or start of next day
        return {
          x: col.x + col.width,
          isClippedLeft: false,
          isClippedRight: false,
        };
      }
    }
  }

  return { x: window.totalWidth, isClippedLeft: false, isClippedRight: true };
}
