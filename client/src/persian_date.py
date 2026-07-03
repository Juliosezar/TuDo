"""Helpers for working with the Jalali (Persian/Iranian, Hijri-Shamsi) calendar.

All todo due dates/times are expressed in this calendar. Storage format uses
zero-padded ISO-like strings (``YYYY-MM-DD`` / ``HH:MM``) so that plain string
sorting/comparison in SQL still works. Display format uses the more common
``D/M/Y`` notation.
"""

from __future__ import annotations

import jdatetime

WEEKDAY_NAMES_FA = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یک‌شنبه"]


def now() -> jdatetime.datetime:
    return jdatetime.datetime.now()


def today() -> jdatetime.date:
    return jdatetime.date.today()


# --------------------------------------------------------------------------
# Storage <-> object conversions
# --------------------------------------------------------------------------


def to_storage_date(d: jdatetime.date) -> str:
    return d.isoformat()


def to_storage_time(t: jdatetime.time) -> str:
    return f"{t.hour:02d}:{t.minute:02d}"


def from_storage_date(value: str) -> jdatetime.date:
    return jdatetime.date.fromisoformat(value)


def from_storage_time(value: str) -> jdatetime.time:
    hour, minute = (int(part) for part in value.split(":"))
    return jdatetime.time(hour, minute)


def to_display_date(d: jdatetime.date) -> str:
    return f"{d.day}/{d.month}/{d.year}"


def to_display_time(t: jdatetime.time) -> str:
    return f"{t.hour:02d}:{t.minute:02d}"


def gregorian_to_display_datetime(iso_value: str) -> str:
    """Convert a stored Gregorian ISO datetime (e.g. from datetime.now()) to a
    human readable Jalali date/time string, for display purposes only."""
    import datetime as _dt

    g = _dt.datetime.fromisoformat(iso_value)
    j = jdatetime.datetime.fromgregorian(datetime=g)
    return f"{to_display_date(j.date())} {to_display_time(j.time())}"


# --------------------------------------------------------------------------
# Relative helpers (--day / --hour)
# --------------------------------------------------------------------------


def add_days(n: int, base: jdatetime.date | None = None) -> jdatetime.date:
    base = base or today()
    return base + jdatetime.timedelta(days=n)


def add_hours(n: int, base: jdatetime.datetime | None = None) -> jdatetime.datetime:
    base = base or now()
    return base + jdatetime.timedelta(hours=n)


# --------------------------------------------------------------------------
# "Nearest" date resolution for --date/-D
# --------------------------------------------------------------------------


def _resolve_day_only(day: int, base: jdatetime.date) -> jdatetime.date:
    month, year = base.month, base.year
    if day < base.day:
        month += 1
        if month > 12:
            month = 1
            year += 1
    return jdatetime.date(year, month, day)


def _resolve_day_month(day: int, month: int, base: jdatetime.date) -> jdatetime.date:
    year = base.year
    if (month, day) < (base.month, base.day):
        year += 1
    return jdatetime.date(year, month, day)


def parse_date_flag(value: str, base: jdatetime.date | None = None) -> jdatetime.date:
    """Parse the value of --date/-D.

    Accepted forms (all Jalali):
      - "today" / "tomorrow"
      - "D"        -> nearest day, this month if it's still ahead, otherwise next month
      - "D/M"      -> nearest day/month, this year if it's still ahead, otherwise next year
      - "D/M/Y"    -> an explicit date, used as-is
    """
    base = base or today()
    text = value.strip().lower()

    if text == "today":
        return base
    if text == "tomorrow":
        return base + jdatetime.timedelta(days=1)

    parts = value.strip().split("/")
    try:
        numbers = [int(p) for p in parts]
    except ValueError:
        raise ValueError(
            f"Invalid date {value!r}. Use D, D/M or D/M/Y (Jalali), 'today' or 'tomorrow'."
        )

    if len(numbers) == 1:
        (day,) = numbers
        return _resolve_day_only(day, base)
    elif len(numbers) == 2:
        day, month = numbers
        return _resolve_day_month(day, month, base)
    elif len(numbers) == 3:
        day, month, year = numbers
        return jdatetime.date(year, month, day)

    raise ValueError(
        f"Invalid date {value!r}. Use D, D/M or D/M/Y (Jalali), 'today' or 'tomorrow'."
    )
