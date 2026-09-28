# AGENT.md

Instructions for AI coding agents working on Cubit. Read this file first, then [REQUIREMENTS.md](REQUIREMENTS.md).

## Project

Cubit is a time-logging tool for a one-person company (IceCube Solutions). It has a CLI and a local web app on one shared core, and stores data as plain text: CSV for entries, YAML for projects and config.

**Status:** all six milestones are built and tested, the macOS menu bar app included. Keep this file up to date as the repo changes, especially the Commands section.

## Source of truth

- `REQUIREMENTS.md` defines what to build (FR-ids), the data formats and the milestones.
- `CHANGELOG.md` records what changed in each version. Add an entry under **Unreleased** for anything a user would notice, and treat a change to a data format as breaking.
- If code and requirements disagree, flag it. Don't silently pick one.
- If you change behaviour or a file format, update `REQUIREMENTS.md` in the same change.

## Stack

Python 3.11+ · Typer (CLI) · Flask + Jinja2 (web) · rumps (macOS menu bar, optional extra) · Pydantic v2 (validation) · ruamel.yaml · filelock · pytest · ruff

## Layout

```
src/cubit/
├── core/          # models, storage, timer, rates, durations, categories, reports
│   ├── models.py      # Pydantic models for every stored shape
│   ├── storage.py     # the only file I/O: CSV, YAML, JSON, locking, atomic writes
│   ├── service.py     # the operations behind the commands, shared by CLI and web
│   ├── reports.py     # pure summaries over entries and projects (FR-17 to FR-22)
│   ├── check.py       # validating a whole folder (FR-41)
│   ├── export.py      # a report as CSV, Markdown or PDF (FR-23, FR-80)
│   ├── pdf.py         # the PDF writer, stdlib only: layout, logo, footer (FR-80)
│   ├── pdf_metrics.py # Helvetica glyph widths, for aligning and wrapping in a PDF
│   ├── durations.py   # duration parsing and formatting (FR-27)
│   ├── categories.py  # normalization, ranking, typo guard (FR-43 to FR-48, FR-52)
│   ├── rates.py       # rate lookup by date and earnings (FR-14, FR-15)
│   ├── timer.py       # elapsed time and stop-to-entry (FR-1 to FR-3, FR-9)
│   └── errors.py      # CubitError and DataFileError
├── cli/           # Typer app
│   ├── main.py        # app, global options, CubitError -> message + hint + exit 1
│   ├── entries.py     # start, stop, status, cancel, add, list, edit, rm
│   ├── projects.py    # project add|list|show|edit|rate|archive|unarchive|rm|category
│   ├── reports.py     # report week|month|project|client|category
│   ├── check.py       # the check command
│   ├── completion.py  # tab-completion values and script (FR-29)
│   ├── prompts.py     # category confirmation and suggestions (FR-45, FR-52, FR-53)
│   ├── output.py      # aligned tables, totals, NO_COLOR (FR-28, FR-59)
│   ├── parsing.py     # option strings -> dates, times, durations, money
│   ├── context.py     # data-folder resolution (FR-26)
│   └── exit_codes.py
├── web/           # Flask app
│   ├── app.py         # the factory: config, CSRF hook, error handler
│   ├── security.py    # CSRF tokens (FR-36)
│   ├── forms.py       # request values -> the types core expects
│   ├── filters.py     # Jinja filters, so templates hold no formatting logic
│   ├── views/         # one blueprint per page, settings included
│   ├── templates/
│   └── static/        # theme.css, app.css, app.js, the logo, fonts/
└── menubar/       # macOS menu bar app (rumps), optional
    ├── model.py       # pure: what the menu says, testable on any OS (FR-71)
    ├── app.py         # the only module that imports rumps
    ├── server.py      # find or start the web app for Open dashboard (FR-68)
    ├── login.py       # the LaunchAgent plist (FR-74)
    └── assets/        # the two template icons, and the app icon (.icns)
tests/
└── fixtures/
    └── sample-data/   # a small realistic data folder used by the tests
design/    # starter theme.css, logo and brand preview (M4); menubar/ icons (M6)
packaging/ # macos/app_icon.svg, the source of the .icns (FR-79)
tools/     # make_icns.sh, run only when the app icon changes
launcher.py            # the app bundle's entry point: CLI with arguments,
                       # menu bar app without (FR-79)
build_macos_app.sh     # Cubit.app + .dmg + .zip into dist/ (FR-79)
```

## Commands

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pip install -e .
pytest
ruff check . && ruff format .
cubit --help
cubit init
cubit project add acme-web --name "Acme website" --client "Acme Corp" --rate 95
cubit start acme-web -c software-coding -m "Landing page"
cubit stop
cubit list
cubit report week
cubit bill --client "Acme Corp"                     # mark unbilled hours as billed
cubit check
cubit web
cubit menubar                                       # macOS only
./build_macos_app.sh                                # Cubit.app + dmg (macOS only)
```

## Architecture rules

1. Business logic lives only in `cubit.core`. CLI and web are thin: parse input, call core, format output. An operation that takes more than one storage call belongs in `core.service`, not in a command.
2. `core` must not import Typer, Flask or rumps, and stays cross-platform.
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
- Time no rate covers is carried as unrated minutes beside the money, never as zero earnings (FR-15).
- Dates are `datetime.date` in local time. The timer's elapsed time is computed from timezone-aware timestamps.
- CLI errors: short message plus hint, non-zero exit code, no traceback.
- Web: server-rendered, no JS build step, no CDN or external requests, bind to `127.0.0.1` only.
- Web: every state-changing route needs a CSRF token, and every form renders `csrf_input()`. There is a test that fails if a route or a form is added without one.
- Web: views never touch files. Anything they need comes from `core.storage` or `core.service`.
- Web: the settings page edits `config.yaml`, which stays a hand-editable file. Build the whole `Config` and validate it before writing, so a rejected value leaves the file as it was, and never write it any way but `storage.save_config`, which keeps the comments.
- Theme: all colors, fonts and spacing are CSS variables in `web/static/theme.css`. No hard-coded colors in templates or other CSS; a test enforces it. Start from `design/theme.css` and use `design/cubit-mark.svg` as logo and favicon. Logo and fonts are bundled locally. Cubit has its own palette (dark default, light variant); see REQUIREMENTS.md 3.8 and 4.5.
- CLI: the category option is `--category` / `-c` and is documented without `#`, since an unquoted `#` starts a shell comment.
- CLI: a command's docstring is its `--help` text, so FR-ids go in a comment beneath it, not in the docstring.
- CLI: every command that can ask something takes `--yes` / `-y`, and nothing is ever asked when stdin is not a terminal.
- macOS: only `menubar/app.py` may import rumps, and it is imported lazily, so every other command works without the extra. Everything the menu shows is decided in `menubar/model.py`, which is pure and tested without macOS (FR-71).
- macOS: every menu callback is wrapped, because an exception in one kills the app with no window to report it in. Errors become a notification and a log line (FR-73).
- macOS: a menu bar click must never wait on the folder lock. Reads do not take it; writes use a short `lock_timeout`.
- macOS: the app bundle is one executable doing two jobs, split in `launcher.py`. Anything that starts a second cubit process must go through `WebServer._command()`, which knows that a frozen app has no `cubit` on its PATH and cannot use `-m` (FR-79).
- macOS: `cubit.icns` is committed. `tools/make_icns.sh` regenerates it from `packaging/macos/app_icon.svg` and is the only step that needs a non-macOS tool, so the build itself never does.
- Keep dependencies minimal. Ask before adding one.

## Testing

- Every requirement with logic gets tests. Reference the FR-id in the test name or docstring where practical.
- Must cover: rate lookup by date, budget calculation, ISO week and month/year boundaries, timers crossing midnight and DST, hand-edited CSV parsing, safe concurrent writes, category normalization, suggestion ranking and auto-registration of new categories, CSRF on every state-changing route, and the menu bar model on a machine that is not a Mac.
- Tests never import rumps. If something can only be tested with a menu bar, it belongs in `menubar/model.py` instead.
- `cubit check` must never write anything, and must keep going past a problem: reporting everything in one pass is the point of it.
- Run `pytest` and `ruff check .` before saying a task is done.

## Working style

- Small, focused changes. Work one milestone at a time (see `REQUIREMENTS.md` section 9).
- If a requirement is ambiguous, ask. Otherwise state your assumptions in the summary.
- Don't build anything from the "Out of scope" list.
- Definition of done: tests pass, ruff is clean, docs updated (README, REQUIREMENTS, AGENT, CHANGELOG), and a manual smoke test of the CLI and web app for user-facing changes.
