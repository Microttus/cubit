"""Validating a whole data folder (FR-41).

Everything else in cubit refuses to work with data it cannot understand: a bad
row stops a load so nothing overwrites it (FR-38). This module does the
opposite. It reads everything it can, catches what it cannot, and returns a
list of problems, so the answer to "what is wrong with my folder" is one
command rather than a series of errors found one at a time.

It never writes anything.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from cubit.core.durations import minutes_between
from cubit.core.errors import CubitError, DataFileError
from cubit.core.models import Entry, Project
from cubit.core.storage import Storage

#: A problem that makes the data wrong, and one that only makes it untidy.
ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Problem:
    """One thing that is wrong, and where to find it."""

    level: str
    code: str
    message: str
    path: Path | None = None
    row: int | None = None

    @property
    def where(self) -> str:
        """The file and row, as a human would write it."""
        if self.path is None:
            return ""
        if self.row is not None:
            return f"{self.path} row {self.row}"
        return str(self.path)

    def __str__(self) -> str:
        where = self.where
        return f"{where}: {self.message}" if where else self.message


@dataclass(frozen=True)
class CheckReport:
    """What a check found, and what it managed to read."""

    problems: list[Problem] = field(default_factory=list)
    projects: int = 0
    entries: int = 0
    months: int = 0

    @property
    def errors(self) -> list[Problem]:
        return [problem for problem in self.problems if problem.level == ERROR]

    @property
    def warnings(self) -> list[Problem]:
        return [problem for problem in self.problems if problem.level == WARNING]

    @property
    def is_clean(self) -> bool:
        return not self.problems

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


def check_data(storage: Storage) -> CheckReport:
    """Read the whole folder and report everything wrong with it (FR-41)."""
    problems: list[Problem] = []

    config_ok = _check_config(storage, problems)
    projects = _load_projects(storage, problems)
    entries, months = _load_entries(storage, problems)

    if projects is not None:
        _check_references(entries, projects, problems)
        _check_categories(entries, projects, problems)
        _check_timer(storage, projects, problems)
    elif config_ok:
        # Without projects.yaml there is nothing to check entries against.
        problems.append(
            Problem(
                WARNING,
                "projects-unreadable",
                "skipped the checks that need projects.yaml",
                path=storage.projects_path,
            )
        )

    _check_ids(entries, problems)
    _check_times(entries, problems)
    _check_billing(entries, problems)

    return CheckReport(
        problems=sorted(problems, key=_reading_order),
        projects=len(projects) if projects else 0,
        entries=sum(len(found) for _, found in entries),
        months=months,
    )


def _reading_order(problem: Problem) -> tuple[str, int, str]:
    """Group a file's problems together, in the order they appear in it."""
    return (str(problem.path or ""), problem.row or 0, problem.code)


def _check_config(storage: Storage, problems: list[Problem]) -> bool:
    try:
        storage.load_config()
    except CubitError as error:
        problems.append(_from_error(error, "config-invalid", storage.config_path))
        return False
    return True


def _load_projects(storage: Storage, problems: list[Problem]) -> list[Project] | None:
    try:
        return storage.load_projects()
    except CubitError as error:
        problems.append(_from_error(error, "projects-invalid", storage.projects_path))
        return None


def _load_entries(
    storage: Storage, problems: list[Problem]
) -> tuple[list[tuple[Path, list[Entry]]], int]:
    """Read every monthly file, keeping going past one that will not parse."""
    loaded: list[tuple[Path, list[Entry]]] = []
    months = storage.months()

    for year, month in months:
        path = storage.month_path(year, month)
        try:
            found = storage.load_month(year, month)
        except CubitError as error:
            problems.append(_from_error(error, "malformed-row", path))
            continue

        loaded.append((path, found))
        for entry in found:
            if (entry.date.year, entry.date.month) != (year, month):
                problems.append(
                    Problem(
                        ERROR,
                        "wrong-month",
                        f"entry {entry.id} is dated {entry.date}, "
                        f"which belongs in {entry.date.year:04d}-{entry.date.month:02d}.csv",
                        path=path,
                    )
                )
    return loaded, len(months)


def _check_ids(entries: list[tuple[Path, list[Entry]]], problems: list[Problem]) -> None:
    """An id has to be unique across every file, not just its own (4.1)."""
    seen: dict[str, Path] = {}
    for path, found in entries:
        for entry in found:
            if entry.id in seen:
                first = seen[entry.id]
                where = (
                    "appears more than once in this file"
                    if first == path
                    else f"is also used in {first.name}"
                )
                problems.append(
                    Problem(ERROR, "duplicate-id", f"entry id {entry.id} {where}", path=path)
                )
            else:
                seen[entry.id] = path


def _check_references(
    entries: list[tuple[Path, list[Entry]]],
    projects: list[Project],
    problems: list[Problem],
) -> None:
    """Every entry points at a project that exists (FR-40)."""
    known = {project.id for project in projects}
    for path, found in entries:
        for entry in found:
            if entry.project_id not in known:
                problems.append(
                    Problem(
                        ERROR,
                        "unknown-project",
                        f"entry {entry.id} is logged against {entry.project_id!r}, "
                        "which is not in projects.yaml",
                        path=path,
                    )
                )


def _check_categories(
    entries: list[tuple[Path, list[Entry]]],
    projects: list[Project],
    problems: list[Problem],
) -> None:
    """Categories an entry uses should be registered on its project (FR-44)."""
    registered = {project.id: set(project.categories) for project in projects}
    missing: dict[tuple[str, str], int] = {}

    for _, found in entries:
        for entry in found:
            if not entry.category:
                continue
            known = registered.get(entry.project_id)
            if known is not None and entry.category not in known:
                missing[(entry.project_id, entry.category)] = (
                    missing.get((entry.project_id, entry.category), 0) + 1
                )

    for (project_id, category), count in sorted(missing.items()):
        subject = "1 entry uses" if count == 1 else f"{count} entries use"
        problems.append(
            Problem(
                WARNING,
                "unregistered-category",
                f"{subject} #{category} on {project_id}, but it is not registered on the project",
            )
        )


def _check_times(entries: list[tuple[Path, list[Entry]]], problems: list[Problem]) -> None:
    """Start, end and duration should agree (FR-41).

    A warning, not an error: ``duration_minutes`` is the source of truth for
    totals, so a mismatch is worth knowing about but changes no number.
    """
    for path, found in entries:
        for entry in found:
            if entry.start is None or entry.end is None:
                continue
            spanned = minutes_between(entry.start, entry.end)
            if spanned != entry.duration_minutes:
                problems.append(
                    Problem(
                        WARNING,
                        "duration-mismatch",
                        f"entry {entry.id} runs {entry.start:%H:%M}-{entry.end:%H:%M} "
                        f"({spanned}m) but its duration says {entry.duration_minutes}m",
                        path=path,
                    )
                )


def _check_billing(entries: list[tuple[Path, list[Entry]]], problems: list[Problem]) -> None:
    """Work cannot be invoiced before it was done: likely a typo (FR-81)."""
    for path, found in entries:
        for entry in found:
            if entry.billed_on is not None and entry.billed_on < entry.date:
                problems.append(
                    Problem(
                        WARNING,
                        "billed-before-worked",
                        f"entry {entry.id} is billed on {entry.billed_on.isoformat()}, "
                        f"before the work on {entry.date.isoformat()}",
                        path=path,
                    )
                )


def _check_timer(storage: Storage, projects: list[Project], problems: list[Problem]) -> None:
    """A running timer has to point at a project that still exists (FR-8)."""
    try:
        state = storage.read_timer()
    except CubitError as error:
        problems.append(_from_error(error, "timer-invalid", storage.timer_path))
        return

    if state is None:
        return

    known = {project.id: project for project in projects}
    project = known.get(state.project_id)
    if project is None:
        problems.append(
            Problem(
                ERROR,
                "unknown-project",
                f"the running timer is on {state.project_id!r}, which is not in projects.yaml",
                path=storage.timer_path,
            )
        )
    elif not project.is_active:
        problems.append(
            Problem(
                WARNING,
                "archived-timer",
                f"the running timer is on {project.id}, which is archived",
                path=storage.timer_path,
            )
        )


def _from_error(error: CubitError, code: str, fallback: Path) -> Problem:
    """Turn a load failure into a problem, keeping the file and row it named."""
    if isinstance(error, DataFileError):
        return Problem(
            ERROR,
            code,
            error.message.split(": ", 1)[-1] if ": " in error.message else error.message,
            path=error.path,
            row=error.row,
        )
    return Problem(ERROR, code, error.message, path=fallback)


def describe(problems: Iterable[Problem]) -> list[str]:
    """One readable line per problem, for a CLI or a web page."""
    return [str(problem) for problem in problems]
