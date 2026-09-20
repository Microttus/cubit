"""What the menu should say, worked out without any macOS at all (FR-71).

The menu bar app holds no business logic. Everything it displays -- the title
beside the icon, which projects and categories to offer, the totals, what a
running timer looks like and what to show when the data will not load -- is
decided here, from :mod:`cubit.core`, by functions that run anywhere. The rumps
layer only draws the result.

Nothing in this module imports rumps, and nothing here writes to disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

from cubit.core import (
    CubitError,
    Entry,
    Project,
    Storage,
    TimerState,
    elapsed_minutes,
    find_entries,
    suggest_categories,
    week_bounds,
)

#: At most this many projects in the Start timer submenu (FR-65).
MAX_PROJECTS = 8

#: What the menu says when the data folder will not load (FR-73).
DATA_PROBLEM = "Data problem: run `cubit check`"

#: Shown instead of a project list when there are no projects yet.
NO_PROJECTS = "No active projects"

LABEL_NO_CATEGORY = "No category"
LABEL_NEW_CATEGORY = "New category..."


class Icon(StrEnum):
    """Which template image the menu bar shows (FR-64, FR-72)."""

    IDLE = "idle"
    RUNNING = "running"


class Choice(StrEnum):
    """What picking a category item means."""

    CATEGORY = "category"
    NONE = "none"
    NEW = "new"


@dataclass(frozen=True)
class CategoryChoice:
    """One item in a project's category submenu (FR-65)."""

    label: str
    kind: Choice = Choice.CATEGORY
    category: str | None = None


@dataclass(frozen=True)
class ProjectChoice:
    """One project in the Start timer submenu, with its categories."""

    project_id: str
    label: str
    categories: list[CategoryChoice] = field(default_factory=list)


@dataclass(frozen=True)
class RunningTimer:
    """The three lines shown while a timer runs (FR-66)."""

    project_id: str
    project_label: str
    category: str | None
    started_at: datetime
    elapsed_minutes: int

    @property
    def heading(self) -> str:
        """``acme-web  #software-coding``, or just the project."""
        if self.category:
            return f"{self.project_label}  #{self.category}"
        return self.project_label

    @property
    def detail(self) -> str:
        """``Since 09:05  -  1:24``."""
        since = self.started_at.astimezone().strftime("%H:%M")
        return f"Since {since}  -  {format_hm(self.elapsed_minutes)}"


@dataclass(frozen=True)
class MenuModel:
    """Everything the menu needs, and nothing about how it is drawn."""

    title: str = ""
    icon: Icon = Icon.IDLE
    running: RunningTimer | None = None
    projects: list[ProjectChoice] = field(default_factory=list)
    today_minutes: int = 0
    week_minutes: int = 0
    error: str | None = None

    @property
    def is_running(self) -> bool:
        return self.running is not None

    @property
    def today_text(self) -> str:
        """Today's total as ``H:MM`` (FR-67)."""
        return format_hm(self.today_minutes)

    @property
    def week_text(self) -> str:
        """This week's total as ``H:MM`` (FR-67)."""
        return format_hm(self.week_minutes)

    @property
    def has_projects(self) -> bool:
        return bool(self.projects)


def format_hm(minutes: int) -> str:
    """Whole minutes as ``H:MM``, the shape a menu bar has room for.

    ``205`` becomes ``3:25`` and ``850`` becomes ``14:10``. Hours are not
    padded, because the menu bar should not be wider than it has to be.
    """
    total = max(int(minutes), 0)
    return f"{total // 60}:{total % 60:02d}"


def build_menu(
    storage: Storage,
    *,
    now: datetime | None = None,
    today: date | None = None,
) -> MenuModel:
    """Read the data folder and work out the whole menu (FR-71).

    Anything that goes wrong reading or parsing the folder comes back as a
    model carrying :data:`DATA_PROBLEM` rather than an exception, so a callback
    can render it instead of crashing (FR-73).
    """
    try:
        return _build(storage, now=now, today=today)
    except CubitError:
        return MenuModel(error=DATA_PROBLEM)


def _build(
    storage: Storage,
    *,
    now: datetime | None,
    today: date | None,
) -> MenuModel:
    config = storage.load_config()
    projects = storage.load_projects()
    by_id = {project.id: project for project in projects}
    state = storage.read_timer()

    day = today or date.today()
    week_start, week_end = week_bounds(day, config.week_starts_on)
    # One read covers both totals: today is inside this week.
    week_entries = find_entries(storage, start=week_start, end=week_end)
    history = storage.load_all_entries()

    running = _running(state, by_id, now=now) if state is not None else None

    return MenuModel(
        title=menu_title(running, config.menubar_title),
        icon=Icon.RUNNING if running else Icon.IDLE,
        running=running,
        projects=project_choices(projects, history),
        today_minutes=sum(e.duration_minutes for e in week_entries if e.date == day),
        week_minutes=sum(e.duration_minutes for e in week_entries),
    )


def _running(
    state: TimerState,
    projects: dict[str, Project],
    *,
    now: datetime | None,
) -> RunningTimer:
    project = projects.get(state.project_id)
    return RunningTimer(
        project_id=state.project_id,
        project_label=project.name if project else state.project_id,
        category=state.category,
        started_at=state.started_at,
        elapsed_minutes=elapsed_minutes(state, now),
    )


def menu_title(running: RunningTimer | None, style: str) -> str:
    """The text beside the icon, per ``menubar_title`` (FR-64).

    Only a running timer gets a title; idle is the icon alone, so the menu bar
    stays quiet when there is nothing to report.
    """
    if running is None or style == "none":
        return ""
    elapsed = format_hm(running.elapsed_minutes)
    if style == "project-time":
        return f"{running.project_id} {elapsed}"
    return elapsed


def project_choices(
    projects: list[Project],
    entries: list[Entry],
    *,
    limit: int = MAX_PROJECTS,
) -> list[ProjectChoice]:
    """The Start timer submenu: active projects, most recently used (FR-65).

    Archived projects are not offered, the same way they are hidden from every
    other picker (FR-13).
    """
    active = [project for project in projects if project.is_active]
    ordered = rank_projects(active, entries)[:limit]
    return [
        ProjectChoice(
            project_id=project.id,
            label=project.name,
            categories=category_choices(project, entries),
        )
        for project in ordered
    ]


def rank_projects(projects: list[Project], entries: list[Entry]) -> list[Project]:
    """Order projects the way categories are ordered (FR-46, FR-65).

    Most recently used first, ties broken by how often, then by name; projects
    with nothing logged against them come last, alphabetically.
    """
    last_used: dict[str, tuple[date, str]] = {}
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry.project_id] = counts.get(entry.project_id, 0) + 1
        moment = (entry.date, entry.id)
        if entry.project_id not in last_used or moment > last_used[entry.project_id]:
            last_used[entry.project_id] = moment

    used = [project for project in projects if project.id in counts]
    unused = [project for project in projects if project.id not in counts]

    used.sort(key=lambda project: project.name.casefold())
    used.sort(key=lambda project: (last_used[project.id], counts[project.id]), reverse=True)
    unused.sort(key=lambda project: project.name.casefold())
    return used + unused


def category_choices(project: Project, entries: list[Entry]) -> list[CategoryChoice]:
    """A project's categories in suggestion order, then the two extras (FR-65).

    The ordering is core's, so the menu bar suggests exactly what the CLI and
    the web app do (FR-46).
    """
    ranked = suggest_categories(project, entries)
    items = [CategoryChoice(label=f"#{name}", category=name) for name in ranked]
    items.append(CategoryChoice(label=LABEL_NO_CATEGORY, kind=Choice.NONE))
    items.append(CategoryChoice(label=LABEL_NEW_CATEGORY, kind=Choice.NEW))
    return items
