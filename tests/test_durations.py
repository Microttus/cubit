"""FR-27: duration input accepts 90m, 1h30m, 1.5h and 1:30."""

from __future__ import annotations

from datetime import time

import pytest

from cubit.core import DurationError, format_duration, minutes_between, parse_duration
from cubit.core.durations import format_hours


@pytest.mark.parametrize(
    ("text", "minutes"),
    [
        ("90m", 90),
        ("1h30m", 90),
        ("1.5h", 90),
        ("1:30", 90),
        ("1h", 60),
        ("45m", 45),
        ("0:45", 45),
        ("2h05m", 125),
        ("90", 90),
        ("1,5h", 90),
        ("  1h 30m  ", 90),
        ("1H30M", 90),
        ("30min", 30),
        ("24:00", 1440),
        ("0.25h", 15),
    ],
)
def test_parse_duration_accepts_the_documented_forms(text: str, minutes: int) -> None:
    assert parse_duration(text) == minutes


@pytest.mark.parametrize("text", ["", "   ", "abc", "1x", "h", "-30m", "1:60", "1:5m", "0m", "0"])
def test_parse_duration_rejects_nonsense(text: str) -> None:
    with pytest.raises(DurationError):
        parse_duration(text)


def test_parse_duration_rounds_to_the_nearest_minute() -> None:
    # Whole minutes are the source of truth, so fractions round rather than
    # accumulating seconds nobody can see in the CSV.
    assert parse_duration("1.51h") == 91
    assert parse_duration("0.51m") == 1


def test_duration_error_carries_a_hint() -> None:
    with pytest.raises(DurationError) as caught:
        parse_duration("later")
    assert caught.value.hint
    assert "1h30m" in caught.value.hint


@pytest.mark.parametrize(
    ("minutes", "text"),
    [(90, "1h30m"), (45, "45m"), (60, "1h"), (0, "0m"), (125, "2h05m")],
)
def test_format_duration(minutes: int, text: str) -> None:
    assert format_duration(minutes) == text


def test_format_hours() -> None:
    assert format_hours(90) == "1.50"
    assert format_hours(45) == "0.75"


def test_minutes_between_wraps_past_midnight() -> None:
    """FR-9: a timer that ran past midnight stores end before start."""
    assert minutes_between(time(9, 5), time(10, 35)) == 90
    assert minutes_between(time(23, 40), time(0, 25)) == 45
