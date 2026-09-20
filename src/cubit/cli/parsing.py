"""Turning command-line strings into the types core expects.

Every failure here is a :class:`~cubit.core.CubitError`, so the user gets a
short message and a hint instead of a traceback (FR-25).
"""

from __future__ import annotations

from datetime import date, time, timedelta
from decimal import Decimal, InvalidOperation

from cubit.core import CubitError, parse_duration

__all__ = ["parse_day", "parse_hours", "parse_minutes", "parse_money", "parse_clock"]


def parse_minutes(text: str) -> int:
    """A duration as whole minutes (FR-27). Raises with a hint on bad input."""
    return parse_duration(text)


def parse_day(text: str | None, *, today: date | None = None) -> date | None:
    """A date as ``YYYY-MM-DD``, or ``today`` / ``yesterday``."""
    if text is None:
        return None
    raw = text.strip().lower()
    now = today or date.today()
    if raw in {"today", "t"}:
        return now
    if raw in {"yesterday", "y"}:
        return now - timedelta(days=1)
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise CubitError(
            f"Cannot read {text!r} as a date.",
            hint="Use YYYY-MM-DD, or 'today' / 'yesterday'.",
        ) from None


def parse_clock(text: str | None) -> time | None:
    """A time of day as ``HH:MM``."""
    if text is None or not text.strip():
        return None
    try:
        parsed = time.fromisoformat(text.strip())
    except ValueError:
        raise CubitError(
            f"Cannot read {text!r} as a time.",
            hint="Use HH:MM, for example 09:05.",
        ) from None
    return time(parsed.hour, parsed.minute)


def parse_money(text: str | None) -> Decimal | None:
    """An hourly rate. Money is Decimal, so the string is parsed directly."""
    if text is None or not text.strip():
        return None
    try:
        value = Decimal(text.strip().replace(",", "."))
    except InvalidOperation:
        raise CubitError(
            f"Cannot read {text!r} as an amount.",
            hint="Use a plain number, for example 95 or 105.50.",
        ) from None
    if value < 0:
        raise CubitError(f"A rate cannot be negative: {text}.")
    return value


def parse_hours(text: str | None) -> Decimal | None:
    """An hour budget, as a plain number of hours."""
    if text is None or not text.strip():
        return None
    try:
        value = Decimal(text.strip().replace(",", "."))
    except InvalidOperation:
        raise CubitError(
            f"Cannot read {text!r} as a number of hours.",
            hint="Use a plain number, for example 120.",
        ) from None
    if value <= 0:
        raise CubitError(f"A budget must be more than zero hours: {text}.")
    return value
