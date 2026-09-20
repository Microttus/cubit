"""FR-2, FR-3 and FR-9: elapsed time, midnight and DST."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from cubit.core import TimerState, elapsed_minutes, elapsed_seconds, entry_from_timer

OSLO = ZoneInfo("Europe/Oslo")


def _timer(started_at: datetime, **kwargs) -> TimerState:
    return TimerState(project_id="acme-web", started_at=started_at, **kwargs)


def test_elapsed_minutes_rounds_to_the_nearest_minute() -> None:
    started = datetime(2026, 9, 18, 9, 0, tzinfo=OSLO)
    state = _timer(started)
    assert elapsed_minutes(state, started + timedelta(minutes=29, seconds=29)) == 29
    assert elapsed_minutes(state, started + timedelta(minutes=29, seconds=30)) == 30


def test_elapsed_minutes_never_goes_below_one() -> None:
    """Entries need at least one minute, so a very short timer still logs one."""
    started = datetime(2026, 9, 18, 9, 0, tzinfo=OSLO)
    assert elapsed_minutes(_timer(started), started + timedelta(seconds=3)) == 1


def test_elapsed_seconds_for_the_live_display() -> None:
    started = datetime(2026, 9, 18, 9, 0, tzinfo=OSLO)
    assert elapsed_seconds(_timer(started), started + timedelta(seconds=125)) == 125


def test_elapsed_requires_an_aware_now() -> None:
    state = _timer(datetime(2026, 9, 18, 9, 0, tzinfo=OSLO))
    with pytest.raises(ValueError, match="timezone-aware"):
        elapsed_minutes(state, datetime(2026, 9, 18, 10, 0))


def test_timer_across_midnight_makes_one_entry_on_the_start_date() -> None:
    """FR-9: the entry belongs to the day the timer started."""
    state = _timer(datetime(2026, 9, 19, 23, 40, tzinfo=OSLO), note="Hotfix")
    entry = entry_from_timer(state, "d90a11", datetime(2026, 9, 20, 0, 25, tzinfo=OSLO))

    assert entry.date == date(2026, 9, 19)
    assert entry.start == time(23, 40)
    assert entry.end == time(0, 25)
    assert entry.duration_minutes == 45
    assert entry.note == "Hotfix"


def test_timer_across_a_month_boundary_stays_on_the_start_date() -> None:
    state = _timer(datetime(2026, 8, 31, 23, 30, tzinfo=OSLO))
    entry = entry_from_timer(state, "9a1b2c", datetime(2026, 9, 1, 0, 30, tzinfo=OSLO))
    assert entry.date == date(2026, 8, 31)
    assert entry.duration_minutes == 60


def test_timer_across_a_year_boundary_stays_on_the_start_date() -> None:
    state = _timer(datetime(2026, 12, 31, 23, 0, tzinfo=OSLO))
    entry = entry_from_timer(state, "000001", datetime(2027, 1, 1, 1, 0, tzinfo=OSLO))
    assert entry.date == date(2026, 12, 31)
    assert entry.duration_minutes == 120


def test_timer_across_the_spring_dst_change_counts_real_time() -> None:
    """01:30 to 03:30 local is one real hour when the clocks jump forward."""
    started = datetime(2026, 3, 29, 1, 30, tzinfo=OSLO)
    stopped = datetime(2026, 3, 29, 3, 30, tzinfo=OSLO)
    assert started.utcoffset() == timedelta(hours=1)
    assert stopped.utcoffset() == timedelta(hours=2)

    entry = entry_from_timer(_timer(started), "000001", stopped)
    assert entry.duration_minutes == 60
    assert entry.start == time(1, 30)
    assert entry.end == time(3, 30)


def test_timer_across_the_autumn_dst_change_counts_real_time() -> None:
    """02:30 happens twice in autumn; the offsets keep the two hours apart."""
    started = datetime(2026, 10, 25, 2, 30, tzinfo=OSLO, fold=0)  # still CEST
    stopped = datetime(2026, 10, 25, 2, 30, tzinfo=OSLO, fold=1)  # already CET
    assert elapsed_minutes(_timer(started), stopped) == 60

    entry = entry_from_timer(_timer(started), "000001", stopped)
    assert entry.duration_minutes == 60
    assert entry.date == date(2026, 10, 25)
    # The stored HH:MM are equal because local time repeats that hour; that is
    # why duration_minutes, not the times, is the source of truth for totals.
    assert entry.start == entry.end == time(2, 30)


def test_entry_from_timer_converts_a_foreign_offset_to_local_time() -> None:
    """A timer started elsewhere still stores local HH:MM (REQUIREMENTS 4.4)."""
    started = datetime(2026, 9, 18, 7, 5, tzinfo=UTC)
    stopped = datetime(2026, 9, 18, 8, 35, tzinfo=UTC)
    entry = entry_from_timer(_timer(started), "a3f9c1", stopped)

    assert entry.duration_minutes == 90
    assert entry.start == time(started.astimezone().hour, started.astimezone().minute)


def test_entry_from_timer_carries_the_timer_category_and_allows_an_override() -> None:
    """FR-1 and FR-2: the timer holds a category, and stop can change it."""
    state = _timer(
        datetime(2026, 9, 18, 9, 5, tzinfo=OSLO), category="software-coding", note="Layout"
    )
    stopped = datetime(2026, 9, 18, 10, 35, tzinfo=OSLO)

    kept = entry_from_timer(state, "a3f9c1", stopped)
    assert kept.category == "software-coding"
    assert kept.note == "Layout"

    changed = entry_from_timer(
        state, "a3f9c1", stopped, category="project-management", note="Client call"
    )
    assert changed.category == "project-management"
    assert changed.note == "Client call"


def test_entry_from_timer_rejects_a_stop_before_the_start() -> None:
    state = _timer(datetime(2026, 9, 18, 9, 5, tzinfo=OSLO))
    with pytest.raises(ValueError, match="before the timer started"):
        entry_from_timer(state, "a3f9c1", datetime(2026, 9, 18, 9, 0, tzinfo=OSLO))
