"""
Property-based tests for the business-hours SLA calculations.

Instead of hand-picked dates, Hypothesis generates many start times, durations and
holiday sets and checks rules that must hold for all of them. Inputs are whole minutes
(seconds = 0): the SLA code works in whole minutes and truncates sub-minute remainders.
"""
from datetime import datetime, timedelta, timezone
import zoneinfo

from hypothesis import HealthCheck, given, settings as hyp_settings, strategies as st

from app.core.config import settings
from app.core.sla import (
    SLA_HOURS_BY_PRIORITY,
    add_business_minutes,
    business_minutes_between,
    calculate_due_at,
)
from app.models.enums import TicketPriority

TZ = zoneinfo.ZoneInfo(settings.WORK_TIMEZONE)
PROFILE = hyp_settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)

# Whole-minute UTC instants across two years
starts = st.datetimes(
    min_value=datetime(2026, 1, 1),
    max_value=datetime(2027, 12, 31),
).map(lambda d: d.replace(second=0, microsecond=0, tzinfo=timezone.utc))

minutes = st.integers(min_value=1, max_value=6000)


@st.composite
def start_and_holidays(draw):
    """A start time plus holidays placed in the three weeks around it, so they actually matter."""
    start = draw(starts)
    window = [start.date() + timedelta(days=i) for i in range(-1, 22)]
    holidays = draw(st.sets(st.sampled_from(window), max_size=14))
    return start, holidays

priorities = st.sampled_from(list(TicketPriority))


def _local(dt: datetime) -> datetime:
    return dt.astimezone(TZ)


@PROFILE
@given(scenario=start_and_holidays(), mins=minutes)
def test_result_is_after_start(scenario, mins):
    start, holidays = scenario
    assert add_business_minutes(start, mins, holidays) > start


@PROFILE
@given(scenario=start_and_holidays(), mins=minutes)
def test_result_falls_inside_working_hours_on_a_working_day(scenario, mins):
    start, holidays = scenario
    local = _local(add_business_minutes(start, mins, holidays))
    assert local.weekday() in settings.WORK_DAYS
    assert local.date() not in holidays
    # Strictly after opening time, and at or before closing time
    assert (local.hour, local.minute) > (9, 0)
    assert (local.hour, local.minute) <= (18, 0)


@PROFILE
@given(scenario=start_and_holidays(), mins=minutes)
def test_counting_back_gives_the_minutes_added(scenario, mins):
    start, holidays = scenario
    end = add_business_minutes(start, mins, holidays)
    assert business_minutes_between(start, end, holidays) == mins


@PROFILE
@given(scenario=start_and_holidays(), a=minutes, b=minutes)
def test_adding_in_two_steps_equals_adding_once(scenario, a, b):
    start, holidays = scenario
    two_steps = add_business_minutes(add_business_minutes(start, a, holidays), b, holidays)
    assert two_steps == add_business_minutes(start, a + b, holidays)


@PROFILE
@given(scenario=start_and_holidays(), a=minutes, b=minutes)
def test_more_minutes_never_ends_earlier(scenario, a, b):
    start, holidays = scenario
    lo, hi = sorted((a, b))
    assert add_business_minutes(start, lo, holidays) <= add_business_minutes(start, hi, holidays)


@PROFILE
@given(
    scenario=start_and_holidays(),
    gap1=st.integers(min_value=0, max_value=20000),
    gap2=st.integers(min_value=0, max_value=20000),
)
def test_business_minutes_between_is_additive(scenario, gap1, gap2):
    start, holidays = scenario
    mid = start + timedelta(minutes=gap1)
    end = mid + timedelta(minutes=gap2)
    whole = business_minutes_between(start, end, holidays)
    assert whole == business_minutes_between(start, mid, holidays) + business_minutes_between(
        mid, end, holidays
    )


@PROFILE
@given(scenario=start_and_holidays(), gap=st.integers(min_value=-5000, max_value=5000))
def test_business_minutes_between_is_never_negative_and_bounded(scenario, gap):
    start, holidays = scenario
    end = start + timedelta(minutes=gap)
    result = business_minutes_between(start, end, holidays)
    assert result >= 0
    assert result <= max(gap, 0)
    if gap <= 0:
        assert result == 0


@PROFILE
@given(scenario=start_and_holidays())
def test_higher_priority_never_has_a_later_due_date(scenario):
    start, holidays = scenario
    due = {p: calculate_due_at(p, start, holidays=holidays) for p in TicketPriority}
    order = sorted(SLA_HOURS_BY_PRIORITY, key=lambda p: SLA_HOURS_BY_PRIORITY[p])
    for sooner, later in zip(order, order[1:]):
        assert due[sooner] <= due[later]
    assert all(d > start for d in due.values())


@PROFILE
@given(scenario=start_and_holidays(), mins=minutes)
def test_naive_datetimes_are_treated_as_utc_and_stay_naive(scenario, mins):
    start, holidays = scenario
    naive = start.replace(tzinfo=None)
    result = add_business_minutes(naive, mins, holidays)
    assert result.tzinfo is None
    assert result.replace(tzinfo=timezone.utc) == add_business_minutes(start, mins, holidays)
