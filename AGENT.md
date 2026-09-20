# AGENT.md

Instructions for AI coding agents working on Cubit. Read this file first, then [REQUIREMENTS.md](REQUIREMENTS.md).

## Project

Cubit is a time-logging tool for a one-person company (IceCube Solutions). It has a CLI and a local web app on one shared core, and stores data as plain text: CSV for entries, YAML for projects and config.

**Status:** design phase, no code yet. Keep this file up to date as the repo takes shape, especially the Commands section.

## Source of truth

- `REQUIREMENTS.md` defines what to build (FR-ids), the data formats and the milestones.
- If code and requirements disagree, flag it. Don't silently pick one.
- If you change behaviour or a file format, update `REQUIREMENTS.md` in the same change.

## Stack

Python 3.11+ · Typer (CLI) · Flask + Jinja2 (web) · Pydantic v2 (validation) · ruamel.yaml · filelock · pytest · ruff

## Layout (planned)

```
src/cubit/
├── core/    # models, storage, timer, rates, durations, reports
├── cli/     # Typer app and commands
└── web/     # Flask app, templates/, static/
tests/
└── fixtures/
design/    # starter theme.css, logo and brand preview (used from Milestone 4)
```

## Commands (planned; confirm once pyproject.toml exists)

```bash
pip install -r requirements-dev.txt
pip install -e .
pytest
ruff check . && ruff format .
cubit --help
cubit web
```

## Architecture rules

1. Business logic lives only in `cubit.core`. CLI and web are thin: parse input, call core, format output.
2. `core` must not import Typer or Flask.
3. All reads and writes of data files go through `core.storage`. No direct `open()` on data files elsewhere.
4. Writes are atomic (temp file + `os.replace`) and held under a file lock, because CLI and web may run at the same time.
5. Reports are pure functions over entries and projects.

## Data-format rules

- Files must stay human-readable and hand-editable.
- Do not rename or reorder CSV columns or YAML keys without a migration note in `REQUIREMENTS.md`.
- Entries reference projects by `id`, never by name.
- Categories are stored as lowercase slugs without `#`. Normalization lives in one function in `core`; the `#` is only display and input sugar.
- Categories are registered per project, but names are shared across projects so reports can total a name across all of them. There are no separate project tags. Suggestion ranking (most recent use, then frequency, then unused) is a pure function in `core`, shared by CLI and web.
- `duration_minutes` is the source of truth for totals.
- Write in stable order (entries by date, start, id) so diffs stay clean.
- On a validation error, report the file and row. Never overwrite or drop the user's data.
- Never commit real time-log data. Tests use `tmp_path` and files in `tests/fixtures/`.

## Conventions

- Type hints everywhere. Format and lint with ruff (line length 100).
- Money is `Decimal`, never `float`. Durations are integer minutes.
- Dates are `datetime.date` in local time. The timer's elapsed time is computed from timezone-aware timestamps.
- CLI errors: short message plus hint, non-zero exit code, no traceback.
- Web: server-rendered, no JS build step, no CDN or external requests, bind to `127.0.0.1` only, CSRF protection on POST.
- Theme: all colors, fonts and spacing are CSS variables in `web/static/theme.css`. No hard-coded colors in templates or other CSS. Start from `design/theme.css` and use `design/cubit-mark.svg` as logo and favicon. Logo and fonts are bundled locally. Cubit has its own palette (dark default, light variant); see REQUIREMENTS.md 3.8 and 4.5.
- CLI: the category option is `--category` / `-c` and is documented without `#`, since an unquoted `#` starts a shell comment.
- Keep dependencies minimal. Ask before adding one.

## Testing

- Every requirement with logic gets tests. Reference the FR-id in the test name or docstring where practical.
- Must cover: rate lookup by date, budget calculation, ISO week and month/year boundaries, timers crossing midnight and DST, hand-edited CSV parsing, safe concurrent writes, category normalization, suggestion ranking and auto-registration of new categories.
- Run `pytest` and `ruff check .` before saying a task is done.

## Working style

- Small, focused changes. Work one milestone at a time (see `REQUIREMENTS.md` section 9).
- If a requirement is ambiguous, ask. Otherwise state your assumptions in the summary.
- Don't build anything from the "Out of scope" list.
- Definition of done: tests pass, ruff is clean, docs updated (README, REQUIREMENTS, AGENT), and a manual smoke test of the CLI and web app for user-facing changes.
