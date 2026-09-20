"""The only place in cubit that reads or writes data files (AGENT.md rule 3).

Every write goes to a temporary file in the same directory and is moved into
place with :func:`os.replace`, while the whole data folder is held under a file
lock, so the CLI and the web app can run at the same time without corrupting
anything (FR-39). Entries are written in a stable order -- date, start, id --
so diffs stay clean (FR-42).

Reading is strict: a file that does not validate raises
:class:`~cubit.core.errors.DataFileError` naming the file and the row or line,
and nothing is written back, so bad data is never silently dropped (FR-38).
"""

from __future__ import annotations

import csv
import io
import json
import os
import secrets
import tempfile
import uuid
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from datetime import date, time
from decimal import Decimal
from pathlib import Path
from typing import Any

from filelock import FileLock
from filelock import Timeout as LockTimeout
from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import YAMLError

from cubit.core.categories import normalize_category
from cubit.core.errors import CubitError, DataFileError, ProjectError
from cubit.core.models import Config, Entry, Project, TimerState

#: Where the data folder lives when nothing else says otherwise (FR-26).
DEFAULT_DATA_DIR = Path.home() / "cubit-data"

#: Environment variable checked before falling back to the default (FR-26).
DATA_DIR_ENV_VAR = "CUBIT_DATA_DIR"

#: Column order of ``entries/YYYY-MM.csv``. Do not reorder: see AGENT.md.
ENTRY_COLUMNS = (
    "id",
    "date",
    "start",
    "end",
    "duration_minutes",
    "project_id",
    "category",
    "note",
)

#: Seconds to wait for another process to release the lock before giving up.
LOCK_TIMEOUT = 10.0

_CONFIG_TEMPLATE = """\
# Cubit configuration. Edit by hand; comments are kept.
currency: NOK                 # any code you like: NOK, EUR, USD, ...
week_starts_on: monday
budget_warning_percent: 80
prompt_for_category: true
theme: dark                   # dark | light | auto
menubar_title: time           # none | time | project-time (macOS menu bar)
"""

_PROJECTS_TEMPLATE = """\
# Cubit projects. Edit by hand; comments are kept.
# Entries reference projects by id, so an id never changes.
projects: []
"""


def resolve_data_dir(
    explicit: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Pick the data folder: ``--data-dir``, then the environment, then the default (FR-26)."""
    if explicit:
        return Path(explicit).expanduser()
    environ = os.environ if env is None else env
    from_env = environ.get(DATA_DIR_ENV_VAR)
    if from_env:
        return Path(from_env).expanduser()
    return DEFAULT_DATA_DIR


def _yaml() -> YAML:
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.representer.add_representer(Decimal, _represent_decimal)
    return yaml


def _represent_decimal(representer: Any, value: Decimal) -> Any:
    text = format(value, "f")
    tag = "tag:yaml.org,2002:float" if "." in text else "tag:yaml.org,2002:int"
    return representer.represent_scalar(tag, text)


class Storage:
    """Read and write one cubit data folder."""

    def __init__(
        self,
        data_dir: str | os.PathLike[str],
        *,
        lock_timeout: float = LOCK_TIMEOUT,
    ) -> None:
        self.data_dir = Path(data_dir).expanduser()
        self.lock_timeout = lock_timeout
        self._yaml = _yaml()
        self._lock = FileLock(str(self.lock_path), timeout=lock_timeout)

    # ------------------------------------------------------------------ paths

    @property
    def config_path(self) -> Path:
        return self.data_dir / "config.yaml"

    @property
    def projects_path(self) -> Path:
        return self.data_dir / "projects.yaml"

    @property
    def entries_dir(self) -> Path:
        return self.data_dir / "entries"

    @property
    def state_dir(self) -> Path:
        return self.data_dir / ".state"

    @property
    def timer_path(self) -> Path:
        return self.state_dir / "timer.json"

    @property
    def lock_path(self) -> Path:
        return self.state_dir / "cubit.lock"

    @property
    def secret_key_path(self) -> Path:
        return self.state_dir / "secret_key"

    def month_path(self, year: int, month: int) -> Path:
        """The entries file a given month lives in."""
        return self.entries_dir / f"{year:04d}-{month:02d}.csv"

    def month_path_for(self, day: date) -> Path:
        return self.month_path(day.year, day.month)

    @property
    def exists(self) -> bool:
        """True once the folder has been initialised."""
        return self.projects_path.exists()

    # ------------------------------------------------------------- lifecycle

    def init(self) -> bool:
        """Create the folder and its starter files. False if it already existed."""
        created = not self.exists
        self.entries_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with self.lock():
            if not self.config_path.exists():
                self._write_atomic(self.config_path, _CONFIG_TEMPLATE)
            if not self.projects_path.exists():
                self._write_atomic(self.projects_path, _PROJECTS_TEMPLATE)
        return created

    @contextmanager
    def lock(self) -> Iterator[None]:
        """Hold the data folder lock (FR-39). Reentrant within one Storage.

        Waiting too long is reported as an ordinary cubit error, so a caller
        that already handles those does not have to know about the lock.
        """
        self.state_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._lock.acquire()
        except LockTimeout:
            raise CubitError(
                "The data folder is busy: another cubit is writing to it.",
                hint="Wait a moment and try again.",
            ) from None
        try:
            yield
        finally:
            self._lock.release()

    def secret_key(self) -> bytes:
        """The key that signs the web app's session cookie.

        Generated on first use and kept in ``.state/`` beside the timer, so it
        is never synced or committed, and readable only by its owner. It has to
        survive a restart, or a form open in the browser would stop working
        every time the server comes back.
        """
        if self.secret_key_path.exists():
            existing = self.secret_key_path.read_bytes().strip()
            if existing:
                return existing

        with self.lock():
            if self.secret_key_path.exists() and self.secret_key_path.read_bytes().strip():
                return self.secret_key_path.read_bytes().strip()
            key = secrets.token_hex(32)
            self._write_atomic(self.secret_key_path, key + "\n")
            self.secret_key_path.chmod(0o600)
            return key.encode("ascii")

    # ----------------------------------------------------------------- config

    def load_config(self) -> Config:
        """Read ``config.yaml``. A missing file means the defaults."""
        if not self.config_path.exists():
            return Config()
        data = self._read_yaml(self.config_path)
        if data is None:
            return Config()
        if not isinstance(data, Mapping):
            raise DataFileError(self.config_path, "expected a mapping of settings")
        try:
            return Config.model_validate(dict(data))
        except ValidationError as exc:
            raise DataFileError(self.config_path, _first_error(exc)) from exc

    def save_config(self, config: Config) -> None:
        """Write ``config.yaml``, keeping the comments already in the file."""
        with self.lock():
            doc = self._read_yaml(self.config_path) if self.config_path.exists() else None
            if not isinstance(doc, CommentedMap):
                doc = CommentedMap()
            for key, value in config.model_dump().items():
                doc[key] = value
            self._write_atomic(self.config_path, self._dump_yaml(doc))

    # --------------------------------------------------------------- projects

    def load_projects(self) -> list[Project]:
        """Read ``projects.yaml`` in file order (FR-11)."""
        if not self.projects_path.exists():
            return []
        doc = self._read_yaml(self.projects_path)
        return self._projects_from(doc)

    def load_projects_map(self) -> dict[str, Project]:
        """The projects keyed by id, for looking up an entry's project (FR-40)."""
        return {project.id: project for project in self.load_projects()}

    def get_project(self, project_id: str) -> Project:
        """One project by id, or :class:`ProjectError` if there is no such project."""
        projects = self.load_projects_map()
        try:
            return projects[project_id]
        except KeyError:
            raise ProjectError(
                f"Unknown project {project_id!r}.",
                hint="Run 'cubit project list' to see the projects you have.",
            ) from None

    def save_projects(self, projects: Iterable[Project]) -> None:
        """Write ``projects.yaml``, keeping comments and hand-written key order."""
        wanted = list(projects)
        with self.lock():
            doc = self._read_yaml(self.projects_path) if self.projects_path.exists() else None
            if not isinstance(doc, CommentedMap):
                doc = CommentedMap()
            existing = doc.get("projects")
            if not isinstance(existing, CommentedSeq):
                existing = CommentedSeq()
            doc["projects"] = _merge_projects(existing, wanted)
            self._write_atomic(self.projects_path, self._dump_yaml(doc))

    def add_project(self, project: Project) -> Project:
        """Add a new project. The id must be free (FR-12)."""
        with self.lock():
            projects = self.load_projects()
            if any(existing.id == project.id for existing in projects):
                raise ProjectError(
                    f"Project {project.id!r} already exists.",
                    hint="Pick another id, or edit the existing project.",
                )
            self.save_projects([*projects, project])
        return project

    def update_project(self, project: Project) -> Project:
        """Replace an existing project, matched on its id."""
        with self.lock():
            projects = self.load_projects()
            if not any(existing.id == project.id for existing in projects):
                raise ProjectError(f"Unknown project {project.id!r}.")
            self.save_projects(
                [project if existing.id == project.id else existing for existing in projects]
            )
        return project

    def register_category(self, project_id: str, name: str) -> Project:
        """Register a category on a project, appending it to the list (FR-45).

        Returns the project unchanged when the category is already registered,
        so callers can call this after every log without extra checks.
        """
        slug = normalize_category(name)
        with self.lock():
            project = self.get_project(project_id)
            if slug in project.categories:
                return project
            updated = project.with_category(slug)
            self.update_project(updated)
            return updated

    # ---------------------------------------------------------------- entries

    def months(self) -> list[tuple[int, int]]:
        """Every month that has an entries file, oldest first."""
        if not self.entries_dir.exists():
            return []
        found: list[tuple[int, int]] = []
        for path in self.entries_dir.glob("*.csv"):
            stem = path.stem
            if len(stem) == 7 and stem[4] == "-" and stem[:4].isdigit() and stem[5:].isdigit():
                found.append((int(stem[:4]), int(stem[5:])))
        return sorted(found)

    def load_month(self, year: int, month: int) -> list[Entry]:
        """Read one monthly file. A missing file is simply no entries."""
        path = self.month_path(year, month)
        if not path.exists():
            return []
        return self._read_entries(path)

    def load_entries(
        self,
        start: date | None = None,
        end: date | None = None,
        *,
        project_id: str | None = None,
        category: str | None = None,
    ) -> list[Entry]:
        """Entries in a date range, sorted by date, start, id.

        Only the monthly files the range touches are opened, so a long history
        stays cheap to report on. ``start`` and ``end`` are inclusive.
        """
        entries: list[Entry] = []
        for year, month in self.months():
            if not _month_in_range(year, month, start, end):
                continue
            entries.extend(self.load_month(year, month))

        def keep(entry: Entry) -> bool:
            if start and entry.date < start:
                return False
            if end and entry.date > end:
                return False
            if project_id and entry.project_id != project_id:
                return False
            return not (category and entry.category != category)

        return sorted((entry for entry in entries if keep(entry)), key=lambda e: e.sort_key)

    def load_all_entries(self) -> list[Entry]:
        """Every entry in the folder, in stable order."""
        return self.load_entries()

    def find_entry(self, entry_id: str) -> Entry | None:
        """Look an entry up by id (FR-7), newest month first."""
        for year, month in reversed(self.months()):
            for entry in self.load_month(year, month):
                if entry.id == entry_id:
                    return entry
        return None

    def save_month(self, year: int, month: int, entries: Iterable[Entry]) -> None:
        """Rewrite one monthly file in stable order (FR-42).

        Writing no entries removes the file, so empty months leave no clutter.
        """
        ordered = sorted(entries, key=lambda entry: entry.sort_key)
        path = self.month_path(year, month)
        with self.lock():
            if not ordered:
                path.unlink(missing_ok=True)
                return
            self.entries_dir.mkdir(parents=True, exist_ok=True)
            self._write_atomic(path, _entries_to_csv(ordered))

    def add_entry(self, entry: Entry) -> Entry:
        """Append an entry to the monthly file its date belongs to (FR-5)."""
        with self.lock():
            existing = self.load_month(entry.date.year, entry.date.month)
            if any(other.id == entry.id for other in existing):
                raise DataFileError(
                    self.month_path_for(entry.date),
                    f"entry id {entry.id!r} is already used",
                )
            self.save_month(entry.date.year, entry.date.month, [*existing, entry])
        return entry

    def update_entry(self, entry: Entry) -> Entry:
        """Replace an entry by id, moving it between months if its date changed (FR-7)."""
        with self.lock():
            old = self.find_entry(entry.id)
            if old is None:
                raise DataFileError(self.entries_dir, f"no entry with id {entry.id!r}")
            if (old.date.year, old.date.month) != (entry.date.year, entry.date.month):
                self._remove_from_month(old)
                return self.add_entry(entry)
            kept = [
                other
                for other in self.load_month(entry.date.year, entry.date.month)
                if other.id != entry.id
            ]
            self.save_month(entry.date.year, entry.date.month, [*kept, entry])
        return entry

    def delete_entry(self, entry_id: str) -> Entry:
        """Delete an entry by id and return it (FR-7)."""
        with self.lock():
            entry = self.find_entry(entry_id)
            if entry is None:
                raise DataFileError(self.entries_dir, f"no entry with id {entry_id!r}")
            self._remove_from_month(entry)
        return entry

    def all_entry_ids(self) -> set[str]:
        """Every entry id in the folder, for uniqueness checks (FR-41)."""
        return {entry.id for entry in self.load_all_entries()}

    def new_entry_id(self) -> str:
        """A fresh six-hex-character id that no entry uses yet."""
        taken = self.all_entry_ids()
        while True:
            candidate = uuid.uuid4().hex[:6]
            if candidate not in taken:
                return candidate

    def _remove_from_month(self, entry: Entry) -> None:
        kept = [
            other
            for other in self.load_month(entry.date.year, entry.date.month)
            if other.id != entry.id
        ]
        self.save_month(entry.date.year, entry.date.month, kept)

    # ------------------------------------------------------------------ timer

    def read_timer(self) -> TimerState | None:
        """The running timer, or ``None`` when no timer is running (FR-8)."""
        if not self.timer_path.exists():
            return None
        try:
            raw = json.loads(self.timer_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DataFileError(
                self.timer_path,
                f"not valid JSON: {exc.msg}",
                line=exc.lineno,
                hint="Delete the file to clear the stuck timer.",
            ) from exc
        if not isinstance(raw, Mapping):
            raise DataFileError(self.timer_path, "expected a JSON object")
        try:
            return TimerState.model_validate(dict(raw))
        except ValidationError as exc:
            raise DataFileError(self.timer_path, _first_error(exc)) from exc

    def write_timer(self, state: TimerState) -> None:
        """Store the running timer, so the CLI and the web app share it (FR-8)."""
        payload = {
            "project_id": state.project_id,
            "started_at": state.started_at.isoformat(),
            "category": state.category,
            "note": state.note,
        }
        with self.lock():
            self.state_dir.mkdir(parents=True, exist_ok=True)
            self._write_atomic(self.timer_path, json.dumps(payload, ensure_ascii=False) + "\n")

    def clear_timer(self) -> None:
        """Remove the timer state file (FR-2, FR-4)."""
        with self.lock():
            self.timer_path.unlink(missing_ok=True)

    # ------------------------------------------------------------- file plumbing

    def _write_atomic(self, path: Path, text: str) -> None:
        """Write via a temp file in the same directory plus :func:`os.replace` (FR-39)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        temp = Path(name)
        try:
            with open(descriptor, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise

    def _read_yaml(self, path: Path) -> Any:
        try:
            return self._yaml.load(path.read_text(encoding="utf-8"))
        except YAMLError as exc:
            raise DataFileError(path, _yaml_message(exc), line=_yaml_line(exc)) from exc

    def _dump_yaml(self, doc: Any) -> str:
        stream = io.StringIO()
        self._yaml.dump(doc, stream)
        return stream.getvalue()

    def _projects_from(self, doc: Any) -> list[Project]:
        path = self.projects_path
        if doc is None:
            return []
        if not isinstance(doc, Mapping):
            raise DataFileError(path, "expected a mapping with a 'projects' key")
        raw = doc.get("projects")
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise DataFileError(path, "'projects' must be a list")

        projects: list[Project] = []
        seen: set[str] = set()
        for index, item in enumerate(raw, start=1):
            if not isinstance(item, Mapping):
                raise DataFileError(path, f"project {index} is not a mapping")
            try:
                project = Project.model_validate(_plain(item))
            except ValidationError as exc:
                name = item.get("id", f"#{index}")
                raise DataFileError(path, f"project {name!r}: {_first_error(exc)}") from exc
            if project.id in seen:
                raise DataFileError(path, f"project id {project.id!r} is used twice")
            seen.add(project.id)
            projects.append(project)
        return projects

    def _read_entries(self, path: Path) -> list[Entry]:
        text = path.read_text(encoding="utf-8-sig")
        reader = csv.reader(io.StringIO(text))
        try:
            header = next(reader)
        except StopIteration:
            return []

        header = [column.strip() for column in header]
        if tuple(header) != ENTRY_COLUMNS:
            raise DataFileError(
                path,
                f"header must be {','.join(ENTRY_COLUMNS)}",
                row=1,
                hint="Columns may not be renamed or reordered.",
            )

        entries: list[Entry] = []
        for row_number, row in enumerate(reader, start=2):
            if not row or all(not cell.strip() for cell in row):
                continue
            if len(row) != len(ENTRY_COLUMNS):
                raise DataFileError(
                    path,
                    f"expected {len(ENTRY_COLUMNS)} columns, found {len(row)}",
                    row=row_number,
                )
            values = dict(zip(ENTRY_COLUMNS, (cell.strip() for cell in row), strict=True))
            entries.append(self._entry_from_row(path, row_number, values))
        return entries

    def _entry_from_row(self, path: Path, row_number: int, values: dict[str, str]) -> Entry:
        try:
            return Entry(
                id=values["id"],
                date=_parse_date(values["date"]),
                start=_parse_time(values["start"]),
                end=_parse_time(values["end"]),
                duration_minutes=_parse_int(values["duration_minutes"], "duration_minutes"),
                project_id=values["project_id"],
                category=values["category"] or None,
                note=values["note"],
            )
        except ValidationError as exc:
            raise DataFileError(path, _first_error(exc), row=row_number) from exc
        except ValueError as exc:
            raise DataFileError(path, str(exc), row=row_number) from exc


# ------------------------------------------------------------------- helpers


def _entries_to_csv(entries: Iterable[Entry]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(ENTRY_COLUMNS)
    for entry in entries:
        writer.writerow(
            [
                entry.id,
                entry.date.isoformat(),
                _format_time(entry.start),
                _format_time(entry.end),
                entry.duration_minutes,
                entry.project_id,
                entry.category or "",
                entry.note,
            ]
        )
    return stream.getvalue()


def _merge_projects(existing: CommentedSeq, wanted: list[Project]) -> CommentedSeq:
    """Update a YAML project list in place so comments on untouched nodes survive."""
    by_id: dict[str, Any] = {}
    for item in existing:
        if isinstance(item, Mapping) and "id" in item:
            by_id[str(item["id"])] = item

    result = CommentedSeq()
    for project in wanted:
        node = by_id.get(project.id)
        result.append(_project_node(project, node))
    return result


def _project_node(project: Project, node: Any) -> CommentedMap:
    """Fill a project's keys into its existing YAML node, or build a fresh one."""
    target = node if isinstance(node, CommentedMap) else CommentedMap()
    # Key order follows the example in REQUIREMENTS 4.2 for files we write from
    # scratch; an existing node keeps whatever order it was hand-written in.
    values: dict[str, Any] = {
        "id": project.id,
        "name": project.name,
        "client": project.client,
        "status": project.status.value,
        "categories": list(project.categories),
    }
    if project.budget_hours is not None:
        values["budget_hours"] = project.budget_hours
    elif "budget_hours" in target:
        del target["budget_hours"]
    values["rates"] = [
        CommentedMap({"valid_from": rate.valid_from, "rate": rate.rate}) for rate in project.rates
    ]

    for key, value in values.items():
        target[key] = value
    return target


def _month_in_range(year: int, month: int, start: date | None, end: date | None) -> bool:
    if start and (year, month) < (start.year, start.month):
        return False
    return not (end and (year, month) > (end.year, end.month))


def _plain(value: Any) -> Any:
    """Strip ruamel's comment-carrying containers down to plain Python."""
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"date {value!r} is not YYYY-MM-DD") from None


def _parse_time(value: str) -> time | None:
    if not value:
        return None
    try:
        parsed = time.fromisoformat(value)
    except ValueError:
        raise ValueError(f"time {value!r} is not HH:MM") from None
    return time(parsed.hour, parsed.minute)


def _parse_int(value: str, column: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"{column} {value!r} is not a whole number") from None


def _format_time(value: time | None) -> str:
    return "" if value is None else f"{value.hour:02d}:{value.minute:02d}"


def _first_error(exc: ValidationError) -> str:
    error = exc.errors()[0]
    location = ".".join(str(part) for part in error["loc"])
    message = error["msg"].removeprefix("Value error, ")
    return f"{location}: {message}" if location else message


def _yaml_message(exc: YAMLError) -> str:
    problem = getattr(exc, "problem", None)
    return f"invalid YAML: {problem}" if problem else "invalid YAML"


def _yaml_line(exc: YAMLError) -> int | None:
    mark = getattr(exc, "problem_mark", None)
    return mark.line + 1 if mark is not None else None
