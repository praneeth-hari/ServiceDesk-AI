export const WORK_TIMEZONE = 'Asia/Kolkata';
export const WORK_TZ_OFFSET_MINUTES = 330; // UTC+05:30

export const WORK_DAY_START_HOUR = 9;
export const WORK_DAY_START_MINUTE = 0;
export const WORK_DAY_END_HOUR = 18;
export const WORK_DAY_END_MINUTE = 0;

export const WORK_MINUTES_PER_DAY = (WORK_DAY_END_HOUR - WORK_DAY_START_HOUR) * 60; // 540 minutes (9 business hours)
export const WORK_DAYS = [1, 2, 3, 4, 5]; // Monday (1) through Friday (5) in JavaScript Date (0 = Sun, 6 = Sat)

export const DEFAULT_TIMELINE_BUSINESS_DAYS = 7;
export const DEFAULT_DAY_WIDTH = 120;
export const DEFAULT_WEEKEND_WIDTH = 32;
export const TIMELINE_ROW_HEIGHT = 44;

