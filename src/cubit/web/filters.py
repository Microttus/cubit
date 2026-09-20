"""Jinja filters and globals, so templates stay free of formatting logic."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from cubit.core import Amount, display_category, format_duration, format_hours


def duration(minutes: int | None) -> str:
    """Whole minutes as ``1h30m``."""
    return format_duration(minutes or 0)


def hours(minutes: int | None) -> str:
    """Whole minutes as decimal hours, for columns that must line up."""
    return format_hours(minutes or 0)


def money(value: Decimal | None, currency: str = "") -> str:
    if value is None:
        return "-"
    return f"{value:.2f} {currency}".strip()


def earned(amount: Amount, currency: str = "") -> str:
    """What an amount earned, saying plainly when part of it had no rate (FR-15)."""
    if not amount.has_earnings:
        return "unrated" if not amount.is_fully_rated else "-"
    return money(amount.earnings, currency)


def category(slug: str | None) -> str:
    """A category as ``#slug``; a dash when there is none."""
    return display_category(slug)


def clock(value: time | None) -> str:
    return "" if value is None else f"{value.hour:02d}:{value.minute:02d}"


def day(value: date | None) -> str:
    return "" if value is None else value.isoformat()


def weekday(value: date | None) -> str:
    return "" if value is None else value.strftime("%a")


def iso(value: datetime | None) -> str:
    return "" if value is None else value.isoformat()


def percent(value: Decimal | float | None) -> str:
    return "-" if value is None else f"{value}%"


FILTERS = {
    "duration": duration,
    "hours": hours,
    "money": money,
    "earned": earned,
    "category": category,
    "clock": clock,
    "day": day,
    "weekday": weekday,
    "iso": iso,
    "percent": percent,
}
