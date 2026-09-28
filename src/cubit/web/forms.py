"""Reading form and query values, and turning them into what core expects.

The CLI has :mod:`cubit.cli.parsing` for the same job; this is its counterpart
for HTTP. Everything that fails raises :class:`~cubit.core.CubitError`, which
the app turns into a flash message.
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal, InvalidOperation

from cubit.core import CubitError, parse_clock, parse_duration


def text(values, name: str, default: str = "") -> str:
    """A trimmed string, or ``default`` when the field was left empty."""
    return (values.get(name) or "").strip() or default


def optional(values, name: str) -> str | None:
    """A trimmed string, or ``None`` when the field was left empty."""
    return text(values, name) or None


def flag(values, name: str) -> bool:
    return text(values, name).lower() in {"1", "true", "on", "yes"}


def required(values, name: str, label: str) -> str:
    value = text(values, name)
    if not value:
        raise CubitError(f"{label} is required.")
    return value


def minutes(values, name: str, label: str = "Duration") -> int:
    """A duration in any of the forms FR-27 accepts."""
    raw = required(values, name, label)
    return parse_duration(raw)


def day(values, name: str, default: date | None = None) -> date | None:
    raw = text(values, name)
    if not raw:
        return default
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise CubitError(f"Cannot read {raw!r} as a date.", hint="Use YYYY-MM-DD.") from None


#: The billing filter's choices, and what find_entries makes of each (FR-81).
BILLING = {"all": None, "unbilled": False, "billed": True}


def billing(values, name: str = "billing") -> bool | None:
    """True for billed entries only, False for unbilled only, None for both."""
    return BILLING.get(text(values, name, "all"))


def many(values, name: str) -> list[str]:
    """Every value of a repeated field, such as the entry ids of a bulk action."""
    return [value.strip() for value in values.getlist(name) if value.strip()]


def clock(values, name: str) -> time | None:
    """A time of day on a 24-hour clock, the same way the CLI reads one."""
    return parse_clock(text(values, name))


def whole(values, name: str, label: str) -> int:
    """A whole number, for a setting like a percentage."""
    raw = required(values, name, label)
    try:
        return int(raw)
    except ValueError:
        raise CubitError(
            f"Cannot read {raw!r} as a whole number.", hint=f"{label} is a number."
        ) from None


def money(values, name: str, label: str) -> Decimal | None:
    raw = text(values, name)
    if not raw:
        return None
    try:
        value = Decimal(raw.replace(",", "."))
    except InvalidOperation:
        raise CubitError(
            f"Cannot read {raw!r} as {label}.", hint="Use a plain number, e.g. 95 or 105.50."
        ) from None
    if value < 0:
        raise CubitError(f"{label} cannot be negative.")
    return value


def hours(values, name: str) -> Decimal | None:
    value = money(values, name, "a number of hours")
    if value is not None and value <= 0:
        raise CubitError("A budget must be more than zero hours.")
    return value
