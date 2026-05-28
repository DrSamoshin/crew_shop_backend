"""Subscription frequency → schedule helpers.

V1 pre-creates a 3-month horizon: weekly → 12 events, biweekly → 6, monthly → 3. The first
event lands one interval ahead of ``today`` so creation never reserves a same-day delivery.
The same horizon is appended when the scheduler extends an active subscription.
"""

import calendar
import enum
from datetime import date, timedelta


class SubscriptionFrequency(enum.StrEnum):
    """Customer-facing delivery cadences."""

    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"


HORIZON_MONTHS = 3
_PERIODIC = {
    SubscriptionFrequency.WEEKLY: (timedelta(days=7), 12),
    SubscriptionFrequency.BIWEEKLY: (timedelta(days=14), 6),
}


def add_months(d: date, months: int) -> date:
    """Add ``months`` calendar months, clamping the day to the resulting month's length."""
    total = d.year * 12 + (d.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def event_dates(today: date, frequency: SubscriptionFrequency) -> list[date]:
    """Schedule of delivery dates for a 3-month horizon, first delivery one interval ahead."""
    if frequency is SubscriptionFrequency.MONTHLY:
        return [add_months(today, i) for i in range(1, HORIZON_MONTHS + 1)]
    interval, count = _PERIODIC[frequency]
    first = today + interval
    return [first + interval * i for i in range(count)]


def next_dates_after(last_date: date, frequency: SubscriptionFrequency) -> list[date]:
    """A horizon-worth of new dates starting one interval after ``last_date`` (for extension)."""
    if frequency is SubscriptionFrequency.MONTHLY:
        return [add_months(last_date, i) for i in range(1, HORIZON_MONTHS + 1)]
    interval, count = _PERIODIC[frequency]
    return [last_date + interval * (i + 1) for i in range(count)]
