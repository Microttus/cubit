"""ISO weeks, month and year boundaries (FR-17, FR-18).

These are the boundary cases AGENT.md calls out: a week that straddles a month
or a year, a leap February, and the Sunday-start option from config.yaml.
"""

from __future__ import annotations

from datetime import date

import pytest

from cubit.core import CubitError, month_bounds, resolve_period, week_bounds, week_label


@pytest.mark.parametrize(
    ("day", "start", "end"),
    [
        (date(2026, 9, 14), date(2026, 9, 14), date(2026, 9, 20)),  # a Monday
        (date(2026, 9, 17), date(2026, 9, 14), date(2026, 9, 20)),  # mid-week
        (date(2026, 9, 20), date(2026, 9, 14), date(2026, 9, 20)),  # a Sunday
    ],
)
def test_week_bounds_start_on_monday(day: date, start: date, end: date) -> None:
    """FR-17: weeks are ISO weeks, Monday to Sunday."""
    assert week_bounds(day) == (start, end)


def test_week_bounds_can_start_on_sunday() -> None:
    """config.yaml may ask for Sunday instead."""
    assert week_bounds(date(2026, 9, 20), "sunday") == (date(2026, 9, 20), date(2026, 9, 26))
    assert week_bounds(date(2026, 9, 19), "sunday") == (date(2026, 9, 13), date(2026, 9, 19))


def test_week_bounds_reject_an_unknown_week_start() -> None:
    with pytest.raises(CubitError) as caught:
        week_bounds(date(2026, 9, 20), "caturday")
    assert "config.yaml" in (caught.value.hint or "")


def test_a_week_can_straddle_a_month():
    """The week of 31 August 2026 runs into September."""
    assert week_bounds(date(2026, 8, 31)) == (date(2026, 8, 31), date(2026, 9, 6))


def test_a_week_can_straddle_a_year() -> None:
    """31 December 2026 is a Thursday, so its week runs into 2027."""
    assert week_bounds(date(2026, 12, 31)) == (date(2026, 12, 28), date(2027, 1, 3))
    assert week_label(date(2026, 12, 31)) == "2026-W53"
    assert week_label(date(2027, 1, 1)) == "2026-W53"  # still the same ISO week


def test_week_label_uses_iso_numbers_only_for_monday_weeks() -> None:
    """A Sunday-start week is not an ISO week, so it is named by its first day."""
    assert week_label(date(2026, 9, 17)) == "2026-W38"
    assert week_label(date(2026, 9, 21), "sunday") == "week of 2026-09-20"


@pytest.mark.parametrize(
    ("day", "start", "end"),
    [
        (date(2026, 9, 18), date(2026, 9, 1), date(2026, 9, 30)),
        (date(2026, 2, 10), date(2026, 2, 1), date(2026, 2, 28)),
        (date(2024, 2, 10), date(2024, 2, 1), date(2024, 2, 29)),  # leap year
        (date(2026, 12, 31), date(2026, 12, 1), date(2026, 12, 31)),
        (date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 31)),
    ],
)
def test_month_bounds(day: date, start: date, end: date) -> None:
    assert month_bounds(day) == (start, end)


def test_resolve_this_and_last_week() -> None:
    today = date(2026, 9, 23)  # a Wednesday
    assert resolve_period("week", "this", today=today) == (date(2026, 9, 21), date(2026, 9, 27))
    assert resolve_period("week", "last", today=today) == (date(2026, 9, 14), date(2026, 9, 20))
    assert resolve_period("week", None, today=today) == (date(2026, 9, 21), date(2026, 9, 27))


def test_resolve_this_and_last_month() -> None:
    today = date(2026, 9, 23)
    assert resolve_period("month", "this", today=today) == (date(2026, 9, 1), date(2026, 9, 30))
    assert resolve_period("month", "last", today=today) == (date(2026, 8, 1), date(2026, 8, 31))


def test_last_month_crosses_the_year() -> None:
    today = date(2026, 1, 15)
    assert resolve_period("month", "last", today=today) == (date(2025, 12, 1), date(2025, 12, 31))


def test_resolve_a_named_week_or_month() -> None:
    assert resolve_period("week", "2026-W39") == (date(2026, 9, 21), date(2026, 9, 27))
    assert resolve_period("week", "2026-w39") == (date(2026, 9, 21), date(2026, 9, 27))
    assert resolve_period("month", "2026-09") == (date(2026, 9, 1), date(2026, 9, 30))


def test_resolve_a_period_from_a_date_inside_it() -> None:
    assert resolve_period("week", "2026-09-23") == (date(2026, 9, 21), date(2026, 9, 27))
    assert resolve_period("month", "2026-09-23") == (date(2026, 9, 1), date(2026, 9, 30))


@pytest.mark.parametrize(
    ("kind", "text"),
    [("week", "bananas"), ("week", "2026-W99"), ("month", "2026-13"), ("month", "soon")],
)
def test_an_unreadable_period_has_a_hint(kind: str, text: str) -> None:
    with pytest.raises(CubitError) as caught:
        resolve_period(kind, text)
    assert caught.value.hint
