from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
import zoneinfo

from app.core.config import settings
from app.models.enums import TicketPriority

# SLA resolution windows in business hours by priority
SLA_HOURS_BY_PRIORITY: dict[TicketPriority, int] = {
    TicketPriority.URGENT: 2,   # 2 business hours: Critical outage
    TicketPriority.HIGH: 8,     # 8 business hours: High-impact issue
    TicketPriority.MEDIUM: 24,  # 24 business hours: Normal issue
    TicketPriority.LOW: 72,     # 72 business hours: Minor request
}


def _get_time_from_str(t_str: str) -> time:
    parts = [int(p) for p in t_str.split(":")]
    return time(parts[0], parts[1])


def _is_work_day(d: date, holidays: set[date]) -> bool:
    return d.weekday() in settings.WORK_DAYS and d not in holidays


def _get_working_start_point(local_dt: datetime, holidays: set[date], tz: zoneinfo.ZoneInfo) -> datetime:
    start_t = _get_time_from_str(settings.WORK_DAY_START)
    end_t = _get_time_from_str(settings.WORK_DAY_END)

    cur_date = local_dt.date()

    # If cur_date is not a work day (weekend or holiday) or if time is at/after end_t:
    if not _is_work_day(cur_date, holidays) or local_dt.time() >= end_t:
        cur_date += timedelta(days=1)
        while not _is_work_day(cur_date, holidays):
            cur_date += timedelta(days=1)
        return datetime.combine(cur_date, start_t, tzinfo=tz)

    # cur_date is a work day, but time is before start_t:
    if local_dt.time() < start_t:
        return datetime.combine(cur_date, start_t, tzinfo=tz)

    # Within working hours on a working day
    return local_dt


def add_business_minutes(
    start_utc: datetime,
    minutes: int,
    holidays: set[date],
) -> datetime:
    """
    Add business minutes to start_utc according to configured WORK_TIMEZONE,
    WORK_DAY_START, WORK_DAY_END, and WORK_DAYS, skipping weekends and holidays.
    """
    was_naive = start_utc.tzinfo is None
    if was_naive:
        start_utc = start_utc.replace(tzinfo=timezone.utc)

    if minutes <= 0:
        res = start_utc
        return res.replace(tzinfo=None) if was_naive else res

    tz = zoneinfo.ZoneInfo(settings.WORK_TIMEZONE)
    start_t = _get_time_from_str(settings.WORK_DAY_START)
    end_t = _get_time_from_str(settings.WORK_DAY_END)

    local_dt = start_utc.astimezone(tz)
    cur_dt = _get_working_start_point(local_dt, holidays, tz)

    rem_min = minutes
    while rem_min > 0:
        day_end = datetime.combine(cur_dt.date(), end_t, tzinfo=tz)
        avail_min = int((day_end - cur_dt).total_seconds() / 60)

        if rem_min <= avail_min:
            cur_dt = cur_dt + timedelta(minutes=rem_min)
            rem_min = 0
            break

        rem_min -= avail_min
        # Roll to next working day start
        next_d = cur_dt.date() + timedelta(days=1)
        while not _is_work_day(next_d, holidays):
            next_d += timedelta(days=1)
        cur_dt = datetime.combine(next_d, start_t, tzinfo=tz)

    res_utc = cur_dt.astimezone(timezone.utc)
    return res_utc.replace(tzinfo=None) if was_naive else res_utc


def add_business_hours(
    start_utc: datetime,
    hours: float | int,
    holidays: set[date],
) -> datetime:
    """
    Add business hours to start_utc.
    """
    return add_business_minutes(start_utc, round(hours * 60), holidays)


def business_minutes_between(
    start_utc: datetime,
    end_utc: datetime,
    holidays: set[date],
) -> int:
    """
    Calculate total business minutes elapsed between start_utc and end_utc.
    Returns 0 if end_utc <= start_utc.
    """
    if start_utc.tzinfo is None:
        start_utc = start_utc.replace(tzinfo=timezone.utc)
    if end_utc.tzinfo is None:
        end_utc = end_utc.replace(tzinfo=timezone.utc)

    if end_utc <= start_utc:
        return 0

    tz = zoneinfo.ZoneInfo(settings.WORK_TIMEZONE)
    start_t = _get_time_from_str(settings.WORK_DAY_START)
    end_t = _get_time_from_str(settings.WORK_DAY_END)

    start_local = start_utc.astimezone(tz)
    end_local = end_utc.astimezone(tz)

    total_minutes = 0
    cur_d = start_local.date()
    end_d = end_local.date()

    while cur_d <= end_d:
        if _is_work_day(cur_d, holidays):
            day_start = datetime.combine(cur_d, start_t, tzinfo=tz)
            day_end = datetime.combine(cur_d, end_t, tzinfo=tz)

            win_start = max(start_local, day_start)
            win_end = min(end_local, day_end)
            if win_end > win_start:
                total_minutes += int((win_end - win_start).total_seconds() / 60)

        cur_d += timedelta(days=1)

    return total_minutes


def calculate_due_at(
    priority: TicketPriority,
    start_time: datetime,
    holidays: Optional[set[date]] = None,
) -> datetime:
    """
    Calculate SLA due_at timestamp by adding the priority's SLA business hours to start_time.
    """
    hours = SLA_HOURS_BY_PRIORITY.get(priority, 24)
    holiday_set = holidays if holidays is not None else set()
    return add_business_hours(start_time, hours, holiday_set)
