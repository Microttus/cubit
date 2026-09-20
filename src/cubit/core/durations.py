"""Duration parsing and formatting (FR-27).

Durations are integer minutes everywhere in cubit; minutes are the source of
truth for every total.
"""

from __future__ import annotations

import re
from datetime import time
from decimal import Decimal, InvalidOperation

from cubit.core.errors import DurationError

#: ``1:30`` / ``0:45`` -- hours and minutes separated by a colon.
_CLOCK = re.compile(r"^(?P<hours>\d+):(?P<minutes>[0-5]?\d)$")

#: ``1h30m`` / ``1h`` / ``90m`` / ``1.5h`` -- a number followed by a unit,
#: optionally an hour part followed by a minute part.
_UNITS = re.compile(
    r"^(?:(?P<hours>\d+(?:[.,]\d+)?)\s*h)?\s*(?:(?P<minutes>\d+(?:[.,]\d+)?)\s*m(?:in)?)?$",
    re.IGNORECASE,
)

_HINT = "Use for example 90m, 1h30m, 1.5h or 1:30."


def parse_duration(text: str) -> int:
    """Parse a human-written duration into whole minutes (FR-27).

    Accepts ``90m``, ``1h30m``, ``1.5h`` and ``1:30``. A bare number is read as
    minutes. Fractional values round to the nearest minute; the result must be
    at least one minute.
    """
    raw = (text or "").strip()
    if not raw:
        raise DurationError("Empty duration.", hint=_HINT)

    clock = _CLOCK.match(raw)
    if clock:
        total = int(clock["hours"]) * 60 + int(clock["minutes"])
        return _validated(total, raw)

    if re.fullmatch(r"\d+(?:[.,]\d+)?", raw):
        # A bare number means minutes.
        return _validated(_round_half_up(_decimal(raw, raw)), raw)

    units = _UNITS.match(raw)
    if not units or not (units["hours"] or units["minutes"]):
        raise DurationError(f"Cannot read {text!r} as a duration.", hint=_HINT)

    total = Decimal(0)
    if units["hours"]:
        total += _decimal(units["hours"], raw) * 60
    if units["minutes"]:
        total += _decimal(units["minutes"], raw)
    return _validated(_round_half_up(total), raw)


def format_duration(minutes: int) -> str:
    """Format whole minutes as ``1h30m`` (``45m`` when under an hour)."""
    if minutes < 0:
        raise DurationError(f"Duration cannot be negative: {minutes}.")
    hours, rest = divmod(int(minutes), 60)
    if hours and rest:
        return f"{hours}h{rest:02d}m"
    if hours:
        return f"{hours}h"
    return f"{rest}m"


def format_hours(minutes: int) -> str:
    """Format whole minutes as decimal hours with two decimals, e.g. ``1.50``."""
    return f"{Decimal(int(minutes)) / 60:.2f}"


def _decimal(value: str, raw: str) -> Decimal:
    try:
        return Decimal(value.replace(",", "."))
    except InvalidOperation as exc:  # pragma: no cover - guarded by the regexes
        raise DurationError(f"Cannot read {raw!r} as a duration.", hint=_HINT) from exc


def _round_half_up(value: Decimal) -> int:
    return int((value + Decimal("0.5")).to_integral_value(rounding="ROUND_FLOOR"))


def _validated(minutes: int, raw: str) -> int:
    if minutes < 1:
        raise DurationError(f"Duration {raw!r} is less than one minute.", hint=_HINT)
    return minutes


#: A time of day: ``9:05`` or ``09:05``, always on a 24-hour clock.
_CLOCK_TIME = re.compile(r"^(?P<hour>\d{1,2}):(?P<minute>\d{2})$")

CLOCK_HINT = "Use a 24-hour time like 09:05 or 17:30."


def parse_clock(text: str | None) -> time | None:
    """Parse a time of day. Blank means no time at all.

    Cubit is 24-hour throughout: entries store ``HH:MM`` and every report and
    menu shows it that way, so ``1:30`` is half past one in the morning, and
    there is no am/pm to get wrong. A single-digit hour is accepted, because a
    text field invites ``9:05``.
    """
    raw = (text or "").strip()
    if not raw:
        return None

    match = _CLOCK_TIME.match(raw)
    if match is None:
        raise DurationError(f"Cannot read {text!r} as a time.", hint=CLOCK_HINT)

    hour, minute = int(match["hour"]), int(match["minute"])
    if hour > 23 or minute > 59:
        raise DurationError(f"{text!r} is not a valid time of day.", hint=CLOCK_HINT)
    return time(hour, minute)


def minutes_between(start: time, end: time) -> int:
    """Whole minutes from ``start`` to ``end``, wrapping past midnight.

    An ``end`` that is not after ``start`` is read as the next day, which is how
    a timer that ran past midnight stores its times (FR-9).
    """
    started = start.hour * 60 + start.minute
    ended = end.hour * 60 + end.minute
    if ended <= started:
        ended += 24 * 60
    return ended - started
