# Changelog

All notable changes to Cubit are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and Cubit uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Because the data files are the interface people actually touch, any change to
the formats in [REQUIREMENTS.md](REQUIREMENTS.md) section 4 counts as a
breaking change and is listed under **Changed** with what to do about it.

## [Unreleased]

### Added

- **macOS menu bar app** (`cubit menubar`), an optional third front end on the
  same files: start and stop the timer from the menu bar, see today's and this
  week's totals, and open the dashboard (FR-63 to FR-75). A timer started here
  shows up in the CLI and the web app, and the other way round.
  - The icon is outlined while idle and solid while running, as monochrome
    template images macOS recolours for a light or dark menu bar (FR-72).
  - `menubar_title` in `config.yaml` sets the text beside the icon: `none`,
    `time` (the default) or `project-time` (FR-64).
  - `cubit menubar install-login` writes a LaunchAgent so it starts at login;
    `uninstall-login` removes it (FR-74).
  - Installed as an extra, macOS only: `pipx install "cubit[menubar]"` (FR-75).
- `/healthz` on the web app, so the menu bar app can tell a cubit server from
  whatever else might be on port 8000 before opening the browser (FR-68).
- **Settings page** in the web app, editing the six settings in `config.yaml`
  through a form (FR-78). Saving validates the whole config before writing, so a
  bad value leaves the file exactly as it was, and the comments in the file
  survive. The page names the folder and the file it edits, because a settings
  page should not hide the file behind it.

### Changed

- `currency` now defaults to `NOK` rather than `EUR`. It was always a setting in
  `config.yaml` and still is; only the default changed, and existing folders are
  untouched because their `config.yaml` already names a currency.
- Times are 24-hour in the web app too. The entry form used `<input type="time">`,
  which a browser draws in its own locale, so a US-locale machine offered an
  am/pm picker for a field cubit stores, prints and reports as `HH:MM`. It is now
  a plain `HH:MM` box, and both the CLI and the web app accept a single-digit
  hour (`9:05`) while refusing `1:30 PM` rather than guessing at it.
- `cubit init` writes `menubar_title` into the starter `config.yaml`, so every
  documented setting is visible to someone editing the file by hand.
- The theme toggle moved from `POST /theme` to `POST /settings/theme`, now that
  settings have a page of their own.
- `currency` cannot be blank: money with no currency reads as a bare number in
  every report.
- `config.yaml` accepts `menubar_title`. REQUIREMENTS 4.3 already documented
  the key, but the config model rejected unknown keys, so a config file written
  to the documented shape did not load. Existing files are unaffected: the key
  is optional and defaults to `time`.
- A write that waits too long for the data-folder lock now raises a normal
  cubit error with a message and a hint, instead of a `filelock` exception. The
  timeout is settable per `Storage`, which is what keeps the menu bar app from
  freezing on a folder another process is writing to.

## [0.1.0] - 2026-09-20

The first working version. Log time from a command line or a local web app,
both over the same plain-text files.

### Added

**Storage and data files**

- Plain-text storage: one CSV per month for entries, `projects.yaml` for
  projects and `config.yaml` for settings, all meant to be edited by hand
  (FR-37).
- Every write goes to a temporary file and is moved into place under a lock, so
  the CLI and the web app can run at the same time without corrupting anything
  (FR-39). Entries are written in a stable order — date, start, id — so diffs
  stay clean (FR-42).
- `projects.yaml` round-trips through `ruamel.yaml`, so comments and hand-written
  key order survive everything the app writes.
- Files are validated on load, and an error names the file and the row. Data
  that does not validate is never overwritten or dropped (FR-38).

**Logging time**

- Start, stop, cancel and show a timer, shared between the CLI and the web app
  (FR-1 to FR-4, FR-8). Elapsed time is computed from a timezone-aware
  timestamp, so it stays right across a DST change, and a timer running past
  midnight produces one entry on the day it started (FR-9).
- Add, list, edit and delete entries by hand, filtered by date, project, client
  and category (FR-5 to FR-7).
- Durations accept `90m`, `1h30m`, `1.5h` and `1:30` (FR-27).
- Logging against an archived project is refused unless forced (FR-10).

**Projects**

- Create, edit, archive, unarchive and delete projects, with a client, an hour
  budget and a rate history (FR-11 to FR-16). A project can only be deleted
  while it has no entries.
- The rate for an entry is the latest rate starting on or before its date, and
  time no rate covers is reported as unrated rather than as zero earnings
  (FR-14, FR-15). `--rate` without `--rate-from` starts today, and both the
  project and the report say so, so backfilled time is never quietly unpaid.

**Categories**

- One optional category per entry, registered per project but totalled across
  projects by name (FR-43 to FR-49, FR-60).
- Names normalize to a lowercase slug, so `Project Management` and
  `#project-management` are the same category (FR-48).
- Using a new category registers it on the project; the CLI asks first, and
  offers the closest existing name if it looks like a typo (FR-45, FR-52).
- Suggestions are ranked by most recent use, then frequency, then unused names
  alphabetically (FR-46).

**Reports**

- Weekly and monthly summaries, broken down by project, client, day, week and
  category (FR-17, FR-18, FR-54, FR-60).
- Per-project reports with hours against the budget, warning at
  `budget_warning_percent` and again once exceeded (FR-19, FR-22, FR-49).
- Per-client and per-category reports (FR-20, FR-61).
- A custom date range and a category filter on every report (FR-21).
- Export any report as CSV or Markdown, from the CLI with `--format` and
  `--output`, or from the web app as a download (FR-23).

**Command line**

- `cubit init`, `start`, `stop`, `status`, `cancel`, `add`, `list`, `edit`,
  `rm`, `check`, `completion`, `web`, and `cubit project` and `cubit report`
  with their subcommands (FR-24).
- The data folder comes from `--data-dir`, then `CUBIT_DATA_DIR`, then
  `~/cubit-data` (FR-26).
- A user error prints a short message and a hint and exits non-zero. No
  tracebacks (FR-25).
- Aligned columns and totals, and the accent colour used sparingly and never
  when `NO_COLOR` is set (FR-28, FR-59).
- `cubit check` validates the whole folder in one pass: malformed rows, unknown
  project ids, duplicate entry ids, entries filed in the wrong month, times
  disagreeing with the duration, unregistered categories and a stale timer
  (FR-41).
- `cubit completion <shell>` writes a tab-completion script for bash, zsh, fish
  or PowerShell, completing project ids, categories, clients and formats
  (FR-29).

**Web app**

- `cubit web` serves a dashboard, entries, projects and reports on
  `127.0.0.1:8000` (FR-30 to FR-34).
- Server-rendered, with no build step and no request to anything outside the
  machine, so it works offline (FR-35).
- Every state-changing request carries a CSRF token, because the loopback
  interface is not a boundary a browser respects (FR-36).
- The category box follows the project selected, and a new name can simply be
  typed (FR-50).

**Look and feel**

- Cubit's own identity: an isometric ice-cube mark and a cyan accent, dark by
  default with a light "ice" variant, switchable from the header and stored in
  `config.yaml` (FR-56, FR-62).
- Every colour, font and spacing value is a CSS variable in one file,
  `web/static/theme.css` (FR-57).
- JetBrains Mono is bundled, under the SIL Open Font License; nothing is
  fetched from the internet (FR-58).

### Notes

- JetBrains Sans is deliberately **not** bundled: its licence does not clearly
  allow redistribution, so body text falls back to Inter and then the system UI
  font. Only the regular weight of JetBrains Mono ships, so bold is synthesized;
  see `src/cubit/web/static/fonts/README.md`.
- Not built in this version, and out of scope for v1: invoicing and PDF export,
  multiple users, cloud sync, a mobile app, a billable flag, free-form entry
  tags, separate client records and calendar integration. Renaming and merging
  categories (FR-55) is only half done — a category can be unregistered, but
  nothing rewrites the entries that use it.

[Unreleased]: https://github.com/Microttus/cubit/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Microttus/cubit/releases/tag/v0.1.0
