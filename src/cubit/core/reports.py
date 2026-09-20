"""Summaries over entries and projects (FR-17 to FR-22, FR-49, FR-54, FR-60).

Every function here is pure: entries and projects in, numbers out. Nothing
reads a file, so the CLI and the web app can load once and summarise many
times, and the tests can build a fortnight of work in memory (AGENT.md rule 5).

Money is always :class:`~decimal.Decimal`, and time that no rate covers is
counted apart rather than as zero, so a report can say "unrated" (FR-15).
"""

from __future__ import annotations

import calendar
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from cubit.core.categories import normalize_optional_category
from cubit.core.errors import CubitError
from cubit.core.models import Entry, Project
from cubit.core.rates import earnings_for_entry

#: The label used for entries with no category (FR-49).
UNCATEGORIZED = "uncategorized"

#: How a week is labelled, and which weekday it starts on.
WEEK_STARTS = {"monday": 0, "sunday": 6}


@dataclass(frozen=True)
class Amount:
    """Time, and what it earned.

    ``unrated_minutes`` are minutes no rate applied to. They are part of
    ``minutes`` but contributed nothing to ``earnings``, so a report can show
    them separately instead of pretending the work was free (FR-15).
    """

    minutes: int = 0
    earnings: Decimal = Decimal("0.00")
    unrated_minutes: int = 0

    @property
    def hours(self) -> Decimal:
        """The time as decimal hours, rounded to two places."""
        return (Decimal(self.minutes) / 60).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def is_fully_rated(self) -> bool:
        return self.unrated_minutes == 0

    @property
    def has_earnings(self) -> bool:
        return self.minutes > self.unrated_minutes


@dataclass(frozen=True)
class Line:
    """One row of a breakdown: what it is, and how much of it there was."""

    key: str
    label: str
    amount: Amount


@dataclass(frozen=True)
class BudgetStatus:
    """How much of a project's hour budget is used (FR-19, FR-22).

    The budget covers the whole project, so it is always measured against every
    hour logged against it, never only the hours in the report's period.
    """

    budget_minutes: int
    used_minutes: int
    warning_percent: int = 80

    @property
    def remaining_minutes(self) -> int:
        """What is left. Negative once the budget is spent."""
        return self.budget_minutes - self.used_minutes

    @property
    def percent_used(self) -> Decimal:
        if self.budget_minutes <= 0:  # pragma: no cover - a budget is always > 0
            return Decimal("0.0")
        ratio = Decimal(self.used_minutes) * 100 / Decimal(self.budget_minutes)
        return ratio.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    @property
    def is_over(self) -> bool:
        return self.used_minutes > self.budget_minutes

    @property
    def is_warning(self) -> bool:
        """At or past the threshold, but not yet over (FR-22)."""
        return not self.is_over and self.percent_used >= self.warning_percent

    @property
    def state(self) -> str:
        if self.is_over:
            return "over"
        return "warning" if self.is_warning else "ok"


@dataclass(frozen=True)
class Summary:
    """A weekly or monthly summary (FR-17, FR-18).

    Every breakdown is worked out, and the caller prints the ones its view
    wants: a week shows days, a month shows weeks and clients, both can show
    categories (FR-54, FR-60).
    """

    start: date
    end: date
    total: Amount
    by_project: list[Line] = field(default_factory=list)
    by_client: list[Line] = field(default_factory=list)
    by_day: list[Line] = field(default_factory=list)
    by_week: list[Line] = field(default_factory=list)
    by_category: list[Line] = field(default_factory=list)
    by_project_category: dict[str, list[Line]] = field(default_factory=dict)
    entries: list[Entry] = field(default_factory=list)


@dataclass(frozen=True)
class ProjectReport:
    """One project over a period, against its budget (FR-19)."""

    project: Project
    start: date | None
    end: date | None
    period: Amount
    total: Amount
    budget: BudgetStatus | None
    by_category: list[Line]
    entries: list[Entry]


@dataclass(frozen=True)
class ClientReport:
    """One client's hours and earnings across their projects (FR-20)."""

    client: str
    start: date | None
    end: date | None
    total: Amount
    by_project: list[Line]
    projects: list[Project]
    entries: list[Entry]


@dataclass(frozen=True)
class CategoryReport:
    """One category name across every project that uses it (FR-61)."""

    category: str
    start: date | None
    end: date | None
    total: Amount
    by_project: list[Line]
    entries: list[Entry]


# ------------------------------------------------------------ periods


def week_bounds(day: date, week_starts_on: str = "monday") -> tuple[date, date]:
    """The first and last day of the week containing ``day`` (FR-17).

    Monday by default, which makes the weeks ISO weeks; ``config.yaml`` can ask
    for Sunday instead.
    """
    try:
        first_weekday = WEEK_STARTS[week_starts_on.lower()]
    except KeyError:
        raise CubitError(
            f"Unknown week start {week_starts_on!r}.",
            hint="Use 'monday' or 'sunday' in config.yaml.",
        ) from None
    offset = (day.weekday() - first_weekday) % 7
    start = day - timedelta(days=offset)
    return start, start + timedelta(days=6)


def month_bounds(day: date) -> tuple[date, date]:
    """The first and last day of ``day``'s month."""
    last = calendar.monthrange(day.year, day.month)[1]
    return day.replace(day=1), day.replace(day=last)


def week_label(day: date, week_starts_on: str = "monday") -> str:
    """How a week is named.

    Monday-start weeks are ISO weeks, so they get the ``2026-W39`` name
    everyone else uses. A Sunday-start week is not an ISO week, so it is named
    after the day it begins instead of borrowing a number that means something
    different.
    """
    start, _ = week_bounds(day, week_starts_on)
    if WEEK_STARTS[week_starts_on.lower()] == 0:
        iso = day.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return f"week of {start.isoformat()}"


def resolve_period(
    kind: str,
    when: str | None = None,
    *,
    today: date | None = None,
    week_starts_on: str = "monday",
) -> tuple[date, date]:
    """Work out the period a report covers.

    ``kind`` is ``week`` or ``month``. ``when`` is ``this`` or ``last``, a date
    inside the period, ``2026-W39`` for a week, or ``2026-09`` for a month.
    """
    now = today or date.today()
    text = (when or "this").strip().lower()
    step = timedelta(days=7) if kind == "week" else None

    if text in {"this", "current"}:
        anchor = now
    elif text in {"last", "previous"}:
        anchor = now - step if step else _previous_month(now)
    else:
        anchor = _parse_anchor(kind, text)

    return week_bounds(anchor, week_starts_on) if kind == "week" else month_bounds(anchor)


def _previous_month(day: date) -> date:
    return day.replace(day=1) - timedelta(days=1)


def _parse_anchor(kind: str, text: str) -> date:
    if kind == "week" and "w" in text:
        year, _, week = text.partition("-w")
        try:
            return date.fromisocalendar(int(year), int(week), 1)
        except ValueError:
            raise CubitError(
                f"Cannot read {text!r} as a week.",
                hint="Use 'this', 'last', a date, or a week like 2026-W39.",
            ) from None

    if kind == "month" and len(text) == 7 and text[4] == "-":
        try:
            return date(int(text[:4]), int(text[5:]), 1)
        except ValueError:
            raise CubitError(
                f"Cannot read {text!r} as a month.",
                hint="Use 'this', 'last', a date, or a month like 2026-09.",
            ) from None

    try:
        return date.fromisoformat(text)
    except ValueError:
        hint = (
            "Use 'this', 'last', a date, or a week like 2026-W39."
            if kind == "week"
            else "Use 'this', 'last', a date, or a month like 2026-09."
        )
        raise CubitError(f"Cannot read {text!r} as a {kind}.", hint=hint) from None


# ------------------------------------------------------------ summaries


def summarize(
    entries: Iterable[Entry],
    projects: Mapping[str, Project],
    *,
    start: date,
    end: date,
    week_starts_on: str = "monday",
    fill_days: bool = False,
) -> Summary:
    """Total a period and break it down every way a summary might show.

    ``by_week`` always covers every week the period touches, so a month shows
    its quiet weeks too. ``by_day`` does the same only when ``fill_days`` is
    set, because a long range would otherwise be mostly empty rows.
    """
    selected = [entry for entry in entries if start <= entry.date <= end]

    by_day = _lines(
        selected,
        projects,
        key=lambda entry: entry.date.isoformat(),
        label=lambda key: key,
        order="key",
    )
    if fill_days:
        by_day = _fill(by_day, [_day.isoformat() for _day in _days_between(start, end)])

    by_week = _fill(
        _lines(
            selected,
            projects,
            key=lambda entry: week_label(entry.date, week_starts_on),
            label=lambda key: key,
            order="key",
        ),
        [week_label(day, week_starts_on) for day in _week_starts(start, end, week_starts_on)],
    )

    return Summary(
        start=start,
        end=end,
        total=total_amount(selected, projects),
        by_project=_project_lines(selected, projects),
        by_client=_client_lines(selected, projects),
        by_day=by_day,
        by_week=by_week,
        by_category=_category_lines(selected, projects),
        by_project_category={
            project_id: _category_lines(group, projects)
            for project_id, group in _grouped(selected, lambda entry: entry.project_id).items()
        },
        entries=selected,
    )


def project_report(
    project: Project,
    entries: Iterable[Entry],
    projects: Mapping[str, Project],
    *,
    start: date | None = None,
    end: date | None = None,
    warning_percent: int = 80,
) -> ProjectReport:
    """One project: its period, its whole history and its budget (FR-19, FR-49).

    ``entries`` may hold every entry there is; only this project's are used.
    """
    own = [entry for entry in entries if entry.project_id == project.id]
    selected = [entry for entry in own if _in_range(entry, start, end)]

    budget = None
    if project.budget_minutes is not None:
        budget = BudgetStatus(
            budget_minutes=project.budget_minutes,
            used_minutes=sum(entry.duration_minutes for entry in own),
            warning_percent=warning_percent,
        )

    return ProjectReport(
        project=project,
        start=start,
        end=end,
        period=total_amount(selected, projects),
        total=total_amount(own, projects),
        budget=budget,
        by_category=_category_lines(selected, projects),
        entries=selected,
    )


def client_report(
    client: str,
    entries: Iterable[Entry],
    projects: Mapping[str, Project],
    *,
    start: date | None = None,
    end: date | None = None,
) -> ClientReport:
    """One client across all of their projects (FR-20)."""
    own = sorted(
        (
            project
            for project in projects.values()
            if project.client.casefold() == client.casefold()
        ),
        key=lambda project: project.id,
    )
    wanted = {project.id for project in own}
    selected = [
        entry for entry in entries if entry.project_id in wanted and _in_range(entry, start, end)
    ]

    return ClientReport(
        client=own[0].client if own else client,
        start=start,
        end=end,
        total=total_amount(selected, projects),
        by_project=_project_lines(selected, projects),
        projects=own,
        entries=selected,
    )


def category_report(
    category: str,
    entries: Iterable[Entry],
    projects: Mapping[str, Project],
    *,
    start: date | None = None,
    end: date | None = None,
) -> CategoryReport:
    """One category name totalled across every project using it (FR-60, FR-61)."""
    slug = normalize_optional_category(category)
    selected = [
        entry for entry in entries if entry.category == slug and _in_range(entry, start, end)
    ]

    return CategoryReport(
        category=slug or UNCATEGORIZED,
        start=start,
        end=end,
        total=total_amount(selected, projects),
        by_project=_project_lines(selected, projects),
        entries=selected,
    )


def total_amount(entries: Iterable[Entry], projects: Mapping[str, Project]) -> Amount:
    """Minutes and money over ``entries``, keeping unrated time apart (FR-15)."""
    minutes = 0
    earned = Decimal("0.00")
    unrated = 0
    for entry in entries:
        minutes += entry.duration_minutes
        project = projects.get(entry.project_id)
        value = earnings_for_entry(project, entry) if project is not None else None
        if value is None:
            unrated += entry.duration_minutes
        else:
            earned += value
    return Amount(minutes=minutes, earnings=earned, unrated_minutes=unrated)


# -------------------------------------------------------------- helpers


def _in_range(entry: Entry, start: date | None, end: date | None) -> bool:
    if start and entry.date < start:
        return False
    return not (end and entry.date > end)


def _grouped(entries: Iterable[Entry], key: Callable[[Entry], str]) -> dict[str, list[Entry]]:
    groups: dict[str, list[Entry]] = {}
    for entry in entries:
        groups.setdefault(key(entry), []).append(entry)
    return groups


def _lines(
    entries: Iterable[Entry],
    projects: Mapping[str, Project],
    *,
    key: Callable[[Entry], str],
    label: Callable[[str], str],
    order: str = "minutes",
) -> list[Line]:
    """Group entries and total each group.

    ``order`` is ``minutes`` for the biggest first, which is what a breakdown
    by project or category wants, or ``key`` for chronological rows.
    """
    lines = [
        Line(key=group_key, label=label(group_key), amount=total_amount(group, projects))
        for group_key, group in _grouped(entries, key).items()
    ]
    if order == "key":
        return sorted(lines, key=lambda line: line.key)
    return sorted(lines, key=lambda line: (-line.amount.minutes, line.label.casefold()))


def _project_lines(entries: Iterable[Entry], projects: Mapping[str, Project]) -> list[Line]:
    def label(project_id: str) -> str:
        project = projects.get(project_id)
        return project.name if project else f"{project_id} (unknown)"

    return _lines(entries, projects, key=lambda entry: entry.project_id, label=label)


def _client_lines(entries: Iterable[Entry], projects: Mapping[str, Project]) -> list[Line]:
    def key(entry: Entry) -> str:
        project = projects.get(entry.project_id)
        return project.client if project and project.client else ""

    return _lines(
        entries,
        projects,
        key=key,
        label=lambda name: name or "no client",
    )


def _category_lines(entries: Iterable[Entry], projects: Mapping[str, Project]) -> list[Line]:
    """A breakdown by category, with uncategorized time included (FR-49)."""
    return _lines(
        entries,
        projects,
        key=lambda entry: entry.category or "",
        label=lambda slug: f"#{slug}" if slug else UNCATEGORIZED,
    )


def _fill(lines: Sequence[Line], keys: Sequence[str]) -> list[Line]:
    """Add empty rows for keys nothing was logged against, in ``keys`` order."""
    known = {line.key: line for line in lines}
    filled = [known.get(key, Line(key=key, label=key, amount=Amount())) for key in keys]
    extra = [line for line in lines if line.key not in set(keys)]
    return filled + sorted(extra, key=lambda line: line.key)


def _days_between(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _week_starts(start: date, end: date, week_starts_on: str) -> list[date]:
    first, _ = week_bounds(start, week_starts_on)
    starts = []
    cursor = first
    while cursor <= end:
        starts.append(cursor)
        cursor += timedelta(days=7)
    return starts
