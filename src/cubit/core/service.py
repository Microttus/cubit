"""The operations a user performs, independent of how they ask for them.

A command like "stop the timer" is several storage calls plus a few rules: is a
timer running, is the project archived, does this category need registering.
That is business logic, so it lives here and both the CLI and the web app call
it rather than each growing their own copy (AGENT.md rule 1).

Every operation that changes something holds the data-folder lock for the whole
read-modify-write, so two interfaces running at once cannot interleave (FR-39).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from cubit.core.categories import closest_category, normalize_category, normalize_optional_category
from cubit.core.errors import CubitError, ProjectError, TimerError
from cubit.core.models import Entry, Project, ProjectStatus, Rate, TimerState
from cubit.core.storage import Storage
from cubit.core.timer import entry_from_timer, now_local


class _Unset:
    """Marker for "this field was not given", so ``None`` can mean "clear it"."""

    def __repr__(self) -> str:  # pragma: no cover - debugging only
        return "UNSET"


#: Sentinel default for optional edits.
UNSET: Any = _Unset()


@dataclass(frozen=True)
class CategoryCheck:
    """What a category name means for a project, before anything is written.

    Pure: the caller decides whether to ask the user (FR-45, FR-52) and then
    passes the name on to an operation, which registers it.
    """

    slug: str
    is_registered: bool
    did_you_mean: str | None = None

    @property
    def is_new(self) -> bool:
        return not self.is_registered


def check_category(project: Project, name: str) -> CategoryCheck:
    """Normalize ``name`` and say whether it is new to ``project`` (FR-45, FR-52)."""
    slug = normalize_category(name)
    if slug in project.categories:
        return CategoryCheck(slug=slug, is_registered=True)
    return CategoryCheck(
        slug=slug,
        is_registered=False,
        did_you_mean=closest_category(slug, project.categories),
    )


def ensure_loggable(project: Project, *, force: bool = False) -> Project:
    """Refuse to log against an archived project unless forced (FR-10)."""
    if project.is_active or force:
        return project
    raise ProjectError(
        f"Project {project.id!r} is archived.",
        hint="Unarchive it, or pass --force to log against it anyway.",
    )


# ------------------------------------------------------------------- timer


def running_timer(storage: Storage) -> TimerState | None:
    """The running timer, or ``None`` (FR-3, FR-8)."""
    return storage.read_timer()


def start_timer(
    storage: Storage,
    project_id: str,
    *,
    category: str | None = None,
    note: str = "",
    force: bool = False,
    now: datetime | None = None,
) -> TimerState:
    """Start the timer for a project (FR-1). Only one may run at a time."""
    with storage.lock():
        already = storage.read_timer()
        if already is not None:
            raise TimerError(
                f"A timer is already running for {already.project_id!r}.",
                hint="Stop it with 'cubit stop', or drop it with 'cubit cancel'.",
            )
        project = ensure_loggable(storage.get_project(project_id), force=force)
        slug = normalize_optional_category(category)
        if slug:
            storage.register_category(project.id, slug)

        state = TimerState(
            project_id=project.id,
            started_at=now or now_local(),
            category=slug,
            note=note,
        )
        storage.write_timer(state)
        return state


def stop_timer(
    storage: Storage,
    *,
    note: str | None = None,
    category: str | None = None,
    now: datetime | None = None,
) -> Entry:
    """Stop the timer and save the entry it produced (FR-2).

    ``note`` and ``category`` override what the timer was started with; leaving
    them out keeps it. The entry lands on the timer's start date (FR-9).
    """
    with storage.lock():
        state = _require_timer(storage)
        slug = normalize_optional_category(category)
        entry = entry_from_timer(
            state,
            storage.new_entry_id(),
            now,
            note=note,
            category=slug,
        )
        if entry.category:
            storage.register_category(state.project_id, entry.category)
        storage.add_entry(entry)
        storage.clear_timer()
        return entry


def cancel_timer(storage: Storage) -> TimerState:
    """Drop the running timer without creating an entry (FR-4)."""
    with storage.lock():
        state = _require_timer(storage)
        storage.clear_timer()
        return state


def _require_timer(storage: Storage) -> TimerState:
    state = storage.read_timer()
    if state is None:
        raise TimerError(
            "No timer is running.",
            hint="Start one with 'cubit start <project>'.",
        )
    return state


# ----------------------------------------------------------------- entries


def add_manual_entry(
    storage: Storage,
    project_id: str,
    duration_minutes: int,
    *,
    day: date | None = None,
    category: str | None = None,
    note: str = "",
    start: time | None = None,
    force: bool = False,
) -> Entry:
    """Log time after the fact (FR-5).

    With a start time the end is worked out from the duration, so the row keeps
    the same start/end/duration shape a timer would have written.
    """
    with storage.lock():
        project = ensure_loggable(storage.get_project(project_id), force=force)
        slug = normalize_optional_category(category)
        if slug:
            storage.register_category(project.id, slug)

        entry = Entry(
            id=storage.new_entry_id(),
            date=day or date.today(),
            start=start,
            end=None if start is None else end_of(start, duration_minutes),
            duration_minutes=duration_minutes,
            project_id=project.id,
            category=slug,
            note=note,
        )
        return storage.add_entry(entry)


def edit_entry(
    storage: Storage,
    entry_id: str,
    *,
    day: date | Any = UNSET,
    duration_minutes: int | Any = UNSET,
    project_id: str | Any = UNSET,
    category: str | None | Any = UNSET,
    note: str | Any = UNSET,
    start: time | None | Any = UNSET,
    force: bool = False,
) -> Entry:
    """Change one entry (FR-7). Only the fields given are touched.

    ``category=None`` clears the category; leaving it out keeps it. Changing the
    start or the duration recomputes the end, so the two never drift apart.
    """
    with storage.lock():
        entry = storage.find_entry(entry_id)
        if entry is None:
            raise CubitError(
                f"No entry with id {entry_id!r}.",
                hint="Run 'cubit list' to see entry ids.",
            )

        changes: dict[str, Any] = {}
        if not isinstance(day, _Unset):
            changes["date"] = day
        if not isinstance(duration_minutes, _Unset):
            changes["duration_minutes"] = duration_minutes
        if not isinstance(note, _Unset):
            changes["note"] = note
        if not isinstance(project_id, _Unset):
            changes["project_id"] = ensure_loggable(storage.get_project(project_id), force=force).id
        if not isinstance(category, _Unset):
            changes["category"] = normalize_optional_category(category)
        if not isinstance(start, _Unset):
            changes["start"] = start

        if not changes:
            return entry

        updated = entry.model_copy(update=changes)
        new_start = updated.start
        if new_start is None:
            updated = updated.model_copy(update={"end": None})
        else:
            updated = updated.model_copy(
                update={"end": end_of(new_start, updated.duration_minutes)}
            )

        if updated.category:
            storage.register_category(updated.project_id, updated.category)
        return storage.update_entry(updated)


def remove_entry(storage: Storage, entry_id: str) -> Entry:
    """Delete one entry (FR-7)."""
    with storage.lock():
        entry = storage.find_entry(entry_id)
        if entry is None:
            raise CubitError(
                f"No entry with id {entry_id!r}.",
                hint="Run 'cubit list' to see entry ids.",
            )
        return storage.delete_entry(entry_id)


def find_entries(
    storage: Storage,
    *,
    start: date | None = None,
    end: date | None = None,
    project_id: str | None = None,
    client: str | None = None,
    category: str | None = None,
) -> list[Entry]:
    """Entries matching the filters, in stable order (FR-6).

    ``client`` matches case-insensitively across all of that client's projects.
    """
    slug = normalize_optional_category(category)
    entries = storage.load_entries(start, end, project_id=project_id, category=slug)
    if client is None:
        return entries

    wanted = {
        project.id
        for project in storage.load_projects()
        if project.client.casefold() == client.casefold()
    }
    return [entry for entry in entries if entry.project_id in wanted]


def end_of(start: time, duration_minutes: int) -> time:
    """The clock time ``duration_minutes`` after ``start``, wrapping past midnight."""
    moment = datetime.combine(date(2000, 1, 1), start) + timedelta(minutes=duration_minutes)
    return time(moment.hour, moment.minute)


# ---------------------------------------------------------------- projects


def create_project(
    storage: Storage,
    project_id: str,
    *,
    name: str,
    client: str = "",
    budget_hours: Decimal | None = None,
    categories: Iterable[str] = (),
    rate: Decimal | None = None,
    rate_from: date | None = None,
) -> Project:
    """Create a project, optionally with its first rate (FR-11)."""
    rates: list[Rate] = []
    if rate is not None:
        rates.append(Rate(valid_from=rate_from or date.today(), rate=rate))
    elif rate_from is not None:
        raise CubitError(
            "A rate start date needs a rate.",
            hint="Pass --rate together with --rate-from.",
        )

    project = Project(
        id=project_id,
        name=name,
        client=client,
        budget_hours=budget_hours,
        categories=list(categories),
        rates=rates,
    )
    return storage.add_project(project)


def edit_project(
    storage: Storage,
    project_id: str,
    *,
    name: str | Any = UNSET,
    client: str | Any = UNSET,
    budget_hours: Decimal | None | Any = UNSET,
) -> Project:
    """Change a project's details (FR-11). The id never changes (FR-12)."""
    with storage.lock():
        project = storage.get_project(project_id)
        changes: dict[str, Any] = {}
        if not isinstance(name, _Unset):
            changes["name"] = name
        if not isinstance(client, _Unset):
            changes["client"] = client
        if not isinstance(budget_hours, _Unset):
            changes["budget_hours"] = budget_hours
        if not changes:
            return project
        return storage.update_project(project.model_copy(update=changes))


def set_rate(
    storage: Storage,
    project_id: str,
    rate: Decimal,
    valid_from: date | None = None,
) -> Project:
    """Add a step to the rate history, replacing one that starts the same day (FR-14)."""
    starts = valid_from or date.today()
    with storage.lock():
        project = storage.get_project(project_id)
        kept = [step for step in project.rates if step.valid_from != starts]
        updated = project.model_copy(update={"rates": [*kept, Rate(valid_from=starts, rate=rate)]})
        return storage.update_project(updated)


def archive_project(storage: Storage, project_id: str) -> Project:
    """Hide a project from pickers, keeping its entries (FR-13)."""
    return _set_status(storage, project_id, ProjectStatus.ARCHIVED)


def unarchive_project(storage: Storage, project_id: str) -> Project:
    """Bring an archived project back (FR-13)."""
    return _set_status(storage, project_id, ProjectStatus.ACTIVE)


def _set_status(storage: Storage, project_id: str, status: ProjectStatus) -> Project:
    with storage.lock():
        project = storage.get_project(project_id)
        if project.status is status:
            return project
        return storage.update_project(project.model_copy(update={"status": status}))


def remove_project(storage: Storage, project_id: str) -> Project:
    """Delete a project, but only while it has no entries (FR-16)."""
    with storage.lock():
        project = storage.get_project(project_id)
        logged = storage.load_entries(project_id=project.id)
        if logged:
            raise ProjectError(
                f"Project {project.id!r} has {len(logged)} entries.",
                hint="Archive it instead with 'cubit project archive'.",
            )
        storage.save_projects(
            [other for other in storage.load_projects() if other.id != project.id]
        )
        return project


def register_project_category(storage: Storage, project_id: str, name: str) -> Project:
    """Register a category on a project up front (FR-44)."""
    return storage.register_category(project_id, name)


def unregister_project_category(storage: Storage, project_id: str, name: str) -> Project:
    """Unregister a category. Entries that already use it are left alone (FR-55)."""
    slug = normalize_category(name)
    with storage.lock():
        project = storage.get_project(project_id)
        if slug not in project.categories:
            raise CubitError(
                f"Project {project.id!r} has no category {slug!r}.",
                hint="Run 'cubit project show' to see its categories.",
            )
        kept = [name for name in project.categories if name != slug]
        return storage.update_project(project.model_copy(update={"categories": kept}))


def active_projects(projects: Sequence[Project]) -> list[Project]:
    """Only the projects that still show up in pickers (FR-13)."""
    return [project for project in projects if project.is_active]
