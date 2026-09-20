"""Pure timer calculations (FR-1 to FR-3, FR-9).

The stored timer keeps a timezone-aware ``started_at``, so elapsed time stays
correct across a DST change. Turning a timer into an entry always assigns it to
its *start* date, which is what makes a timer running past midnight produce one
entry rather than two (FR-9).
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from decimal import ROUND_HALF_UP, Decimal

from cubit.core.models import Entry, TimerState

#: A timer always produces at least one minute, because entries require it.
MIN_TIMER_MINUTES = 1


def now_local() -> datetime:
    """The current time as a timezone-aware local datetime."""
    return datetime.now(UTC).astimezone()


def elapsed_minutes(state: TimerState, now: datetime | None = None) -> int:
    """Whole minutes the timer has been running, rounded to the nearest minute.

    Both sides are timezone-aware, so an hour spent across a DST change counts
    as the hour it really was.
    """
    moment = now or now_local()
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    seconds = Decimal((moment - state.started_at).total_seconds())
    minutes = int((seconds / 60).to_integral_value(rounding=ROUND_HALF_UP))
    return max(minutes, MIN_TIMER_MINUTES)


def elapsed_seconds(state: TimerState, now: datetime | None = None) -> int:
    """Whole seconds the timer has been running, for a live display (FR-3)."""
    moment = now or now_local()
    return int((moment - state.started_at).total_seconds())


def entry_from_timer(
    state: TimerState,
    entry_id: str,
    stopped_at: datetime | None = None,
    *,
    note: str | None = None,
    category: str | None = None,
) -> Entry:
    """Build the entry a timer stop produces (FR-2, FR-9).

    The entry takes the timer's *start* date, and local ``HH:MM`` start and end
    times, so a timer that ran past midnight stays a single entry on the day it
    began. ``note`` and ``category`` override what the timer was started with.
    """
    ended = (stopped_at or now_local()).astimezone()
    if ended < state.started_at:
        raise ValueError("stop time is before the timer started")

    started_local = state.started_at.astimezone()
    return Entry(
        id=entry_id,
        date=started_local.date(),
        start=time(started_local.hour, started_local.minute),
        end=time(ended.hour, ended.minute),
        duration_minutes=elapsed_minutes(state, ended),
        project_id=state.project_id,
        category=state.category if category is None else category,
        note=state.note if note is None else note,
    )
