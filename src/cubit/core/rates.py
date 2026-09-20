"""Hourly-rate lookup and earnings (FR-14, FR-15).

Money is always :class:`~decimal.Decimal`. An entry with no applicable rate has
no earnings at all: these functions return ``None``, never ``0``, so reports can
flag it as "unrated" (FR-15).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from cubit.core.models import Entry, Project

CENTS = Decimal("0.01")


def rate_for_date(project: Project, on: date) -> Decimal | None:
    """The rate that applies on ``on``: the latest one valid on or before it (FR-14).

    ``None`` when the project has no rates, or none had started yet (FR-15).
    """
    applicable = [rate.rate for rate in project.rates if rate.valid_from <= on]
    return applicable[-1] if applicable else None


def earnings(minutes: int, rate: Decimal | None) -> Decimal | None:
    """Money earned by ``minutes`` at ``rate``, rounded to cents.

    ``None`` in, ``None`` out: unrated time has no value (FR-15).
    """
    if rate is None:
        return None
    return (Decimal(int(minutes)) / 60 * rate).quantize(CENTS, rounding=ROUND_HALF_UP)


def earnings_for_entry(project: Project, entry: Entry) -> Decimal | None:
    """Earnings for one entry, using the rate that applied on its date."""
    return earnings(entry.duration_minutes, rate_for_date(project, entry.date))


def is_unrated(project: Project, entry: Entry) -> bool:
    """True when no rate applies to this entry, so reports must flag it (FR-15)."""
    return rate_for_date(project, entry.date) is None


def total_earnings(
    entries: Iterable[Entry],
    projects: dict[str, Project],
) -> tuple[Decimal, int]:
    """Sum earnings over ``entries``.

    Returns the total and the number of minutes that could not be priced, so
    callers can show "1 250.00 EUR + 90m unrated" instead of pretending the
    unrated time is free (FR-15). Entries for an unknown project count as
    unrated.
    """
    total = Decimal("0.00")
    unrated_minutes = 0
    for entry in entries:
        project = projects.get(entry.project_id)
        value = earnings_for_entry(project, entry) if project is not None else None
        if value is None:
            unrated_minutes += entry.duration_minutes
        else:
            total += value
    return total, unrated_minutes
