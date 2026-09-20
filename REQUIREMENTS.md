# Cubit: Requirements

Version: 0.3 (draft for review) · Owner: IceCube Solutions

## 1. Purpose

Cubit is a time-logging application for a single-person company. It records how many hours are worked on which client project, with a short note, and produces summaries of that time. It is used from a command line, from a local web app and, on macOS, from a menu bar icon, all working on the same data.

## 2. Decisions so far

| Topic | Decision |
|---|---|
| Name | **Cubit** (CLI command `cubit`) |
| Users | One person, one machine (for now) |
| Interfaces | CLI **and** local web app, sharing one core, plus an optional macOS menu bar app (3.9) |
| Logging | Start/stop timer **and** manual entry |
| Storage | Plain text, human-readable and editable: CSV (entries), YAML (projects, config), JSON (timer state) |
| Data location | Local folder; sync possible later, not built now |
| Project info | Hourly rate (with history), status (active/archived), hour budget, registered categories |
| Tags vs categories | No separate project tags. Categories cover that need: registered and suggested per project, but totalled across projects by name |
| Entry info | Date, duration, project id, one optional sub-category (e.g. `#software-coding`), note (plus a generated entry id) |
| Reports | Weekly and monthly summaries; per-client and per-project reports |
| Stack | Python 3.11+, Typer, Flask, Pydantic, ruamel.yaml |
| Look and feel | Cubit's own identity (logo, palette), inspired by the IceCube Solutions site. Dark by default, light "ice" variant. Starter files in `design/`, see 3.8 |
| Running on macOS | Installed with `pipx`. Optional menu bar icon (in the style of JetBrains Toolbox) to start and stop the timer, see totals and open the dashboard. Can start at login, see 3.9 |

## 3. Functional requirements

Priorities: **Must** (v1 is not done without it), **Should** (v1 if time allows), **Could** (later).

### 3.1 Time logging

| ID | Pri | Requirement |
|---|---|---|
| FR-1 | Must | Start a timer for a project, with an optional category and note. Only one timer can run at a time. |
| FR-2 | Must | Stop the timer: creates one entry with start, end, duration and note. The note can be set or changed at stop. |
| FR-3 | Must | Show the running timer (project, note, elapsed time). |
| FR-4 | Should | Cancel the running timer without creating an entry. |
| FR-5 | Must | Add an entry manually: project, duration, date (default today), optional category, note, optional start time. |
| FR-6 | Must | List entries, filterable by date range, project, client and category. |
| FR-7 | Must | Edit and delete an entry by its id. |
| FR-8 | Must | Timer state is shared: a timer started in the CLI can be seen and stopped in the web app, and vice versa. |
| FR-9 | Should | A timer that runs past midnight produces a single entry, assigned to its start date. |
| FR-10 | Should | Starting a timer or adding an entry on an archived project is refused unless forced. |

### 3.2 Projects and clients

| ID | Pri | Requirement |
|---|---|---|
| FR-11 | Must | Create, show, list and edit projects with: `id`, `name`, `client`, `status`, `budget_hours` (optional), `rates`, `categories`. |
| FR-12 | Must | The project `id` is a unique lowercase slug and cannot be changed through the app. |
| FR-13 | Must | Archive and unarchive projects. Archived projects are hidden from pickers and default lists, but their entries and reports remain. |
| FR-14 | Must | Rate history: each project has a list of `{valid_from, rate}`. The rate for an entry is the latest rate with `valid_from` on or before the entry date. |
| FR-15 | Must | An entry with no applicable rate has no earnings; reports flag it as "unrated" instead of treating it as 0. |
| FR-16 | Should | A project can only be deleted if it has no entries; otherwise it should be archived. |

### 3.3 Reports

| ID | Pri | Requirement |
|---|---|---|
| FR-17 | Must | **Weekly summary:** total hours, breakdown by project and by day. Weeks are ISO weeks (Monday start by default). |
| FR-18 | Must | **Monthly summary:** total hours, breakdown by project, client and week. |
| FR-19 | Must | **Per-project report:** total hours, hours in selected period, budget used, remaining and %, earnings, entry list. |
| FR-20 | Must | **Per-client report:** hours and earnings across the client's projects, with a per-project breakdown. |
| FR-21 | Should | Any custom date range (`--from`, `--to`) and category filter on all reports. |
| FR-22 | Should | Budget warning at a configurable threshold (default 80%) and when exceeded. |
| FR-23 | Could | Export a report as CSV or Markdown. |

### 3.4 CLI

| ID | Pri | Requirement |
|---|---|---|
| FR-24 | Must | One executable `cubit` with subcommands. Every command has `--help`. |
| FR-25 | Must | User errors give a short message and a hint, and a non-zero exit code. No Python tracebacks. |
| FR-26 | Must | Data folder is chosen by `--data-dir`, then `CUBIT_DATA_DIR`, then the default `~/cubit-data`. |
| FR-27 | Must | Duration input accepts `90m`, `1h30m`, `1.5h` and `1:30`. |
| FR-28 | Should | Tables and summaries are readable in a terminal (aligned columns, totals). |
| FR-29 | Could | Shell tab-completion for commands and project ids. |

### 3.5 Web app

| ID | Pri | Requirement |
|---|---|---|
| FR-30 | Must | `cubit web` starts a server on `127.0.0.1` (default port 8000). |
| FR-31 | Must | **Dashboard:** start/stop timer, today's entries, this week's total. |
| FR-32 | Must | **Entries page:** list with filters, add, edit, delete. |
| FR-33 | Must | **Projects page:** create/edit, rate history, archive/unarchive. |
| FR-34 | Must | **Reports page:** weekly, monthly, per-project and per-client views. |
| FR-35 | Must | Server-rendered pages, no JS build step, no external network requests (works offline). |
| FR-36 | Must | CSRF protection on all state-changing requests. Without it, any website open in the browser could post to the local server. Built with the first POST rather than retrofitted, so no route can be added without it. |
| FR-78 | Should | **Settings page:** the settings in `config.yaml` (4.3) edited in a form. Saving writes the whole file at once and only if every value validates, so a rejected change leaves the file as it was. The file stays hand-editable and keeps its comments (FR-37). The page names the folder and the settings file it is editing. |

### 3.6 Data and storage

| ID | Pri | Requirement |
|---|---|---|
| FR-37 | Must | Data files follow section 4 and are safe to edit by hand. |
| FR-38 | Must | Files are validated on load. Errors name the file and row/line. Invalid data is never overwritten or dropped. |
| FR-39 | Must | Writes are atomic and locked, so the CLI and web app can run at the same time without corruption. |
| FR-40 | Must | Entries reference projects by `id`, never by name. Renaming a project does not affect history. |
| FR-41 | Should | `cubit check` validates the whole folder: unknown project ids, duplicate entry ids, malformed rows, duration/start/end mismatches, categories used by entries but not registered on the project. |
| FR-42 | Should | Files are written in a stable order (entries by date, start, id) so diffs stay clean and the folder works with git or a sync tool. |

### 3.7 Categories (sub-categories per project)

A category classifies the work *inside* one project, for example `#project-management` or `#software-coding`. It replaces the earlier idea of separate project tags: categories are registered and suggested per project, but the same name can be used in several projects, so it can also be totalled across all of them, like a tag.

A category is not a note. A note is free text on a single entry ("Fixed login bug"); a category is a short label you reuse.

| ID | Pri | Requirement |
|---|---|---|
| FR-43 | Must | An entry can have one optional category. |
| FR-44 | Must | Each project has its own list of registered categories in `projects.yaml`. You can register them up front or edit the list by hand. |
| FR-45 | Must | Using a category that isn't registered on the project registers it automatically, so the list grows from real use. In the CLI this asks for confirmation first. |
| FR-46 | Must | When logging (start, add, edit), the project's categories are suggested, ordered by most recent use, then by frequency, then registered-but-unused alphabetically. |
| FR-47 | Must | Categories are per project. The same name in two projects is registered separately, and suggestions only show the selected project's categories. Reports can still total a name across projects (FR-60). |
| FR-48 | Must | Names are normalized to a lowercase slug: `Project Management`, `project management` and `#project-management` all become `project-management`. They are displayed with a leading `#`. |
| FR-49 | Must | Filter entries by category. The per-project report breaks hours (and earnings) down by category, including "uncategorized". |
| FR-50 | Must | Web: the category field is an autocomplete that follows the selected project's suggestions, and a new name can simply be typed. |
| FR-51 | Should | CLI option is `--category` / `-c`. It is documented without `#`, because an unquoted `#` starts a comment in shells such as bash and PowerShell. A leading `#` is accepted when quoted. |
| FR-52 | Should | Typo guard: an unregistered name close to a registered one asks "Did you mean #x?" before creating a new category. |
| FR-53 | Should | In an interactive terminal, `start` and `add` without `-c` show the project's top suggestions as a numbered list. Enter skips. Can be turned off with `prompt_for_category` in `config.yaml`. |
| FR-54 | Should | Weekly and monthly reports can break each project down by category. |
| FR-55 | Could | Rename, merge and remove categories. Rename and merge rewrite affected entries; remove only unregisters the name. |
| FR-60 | Must | Weekly and monthly summaries include hours per category name across all projects (e.g. all `#project-management` time this month). |
| FR-61 | Should | `cubit report category <name>` and a web view show one category across projects, with a per-project split. |

### 3.8 Look and feel

Cubit has its own identity: its own logo and palette, inspired by the IceCube Solutions website ([icecubesol.no](https://icecubesol.no), source in the [SpaceIceWeb repo](https://github.com/Microttus/SpaceIceWeb)) so the two feel related. Kept from the site: near-black backgrounds, the cyan accent, JetBrains Mono, a frosted header with the logo on the left and navigation on the right, 12px rounded cards and pill-shaped chips. The site's looping background video is not used; the app has a static background with a faint accent glow.

Starter files are in `design/`: `cubit-mark.svg` (logo and favicon), `theme.css` (tokens) and `brand-preview.svg` (what it looks like).

| ID | Pri | Requirement |
|---|---|---|
| FR-56 | Must | The web app uses Cubit's own identity from `design/`: logo, palette and fonts, with the logo on the left and navigation on the right (Dashboard, Entries, Projects, Reports, Settings). |
| FR-57 | Must | All colors, fonts and spacing are CSS variables in one file, `web/static/theme.css`, started from `design/theme.css` (see 4.5). No hard-coded colors anywhere else. Changing the theme means editing that file. |
| FR-58 | Must | Logo, favicon and fonts are bundled with the app. Nothing is loaded from the internet (see FR-35). **JetBrains Mono** is the bundled font: it is under the SIL Open Font License, so it may ship with the app, and it sets navigation, durations, totals, ids and `#categories`. Copy the `.woff2` files into `web/static/fonts/` (see the README there). JetBrains **Sans** is not bundled, because its licence does not clearly allow redistribution; body text falls back to Inter and then the system UI font. |
| FR-59 | Should | CLI output uses the accent color sparingly and respects `NO_COLOR`. |
| FR-62 | Should | Dark theme by default, light "ice" theme available. `theme: dark \| light \| auto` in `config.yaml`, plus a toggle in the header. |

### 3.9 macOS menu bar app

An optional app for macOS, in the style of JetBrains Toolbox: an icon at the top right of the menu bar that opens a small menu. It is a third front end on the same core, so a timer started here shows up in the CLI and the web app, and the other way round. The core, CLI and web app stay cross-platform.

Idle:

```
Cubit
------------------------------
Start timer        >  acme-web   >  #software-coding
                      internal      #project-management
                      ...           No category
                                    New category...
------------------------------
Today            3:25
This week       14:10
------------------------------
Open dashboard
Quit Cubit
```

Running (the menu bar shows the solid icon and, for example, `1:24`):

```
acme-web  #software-coding
Since 09:05  -  1:24
Stop timer...
Cancel timer
------------------------------
Today            3:25
This week       14:10
------------------------------
Open dashboard
Quit Cubit
```

| ID | Pri | Requirement |
|---|---|---|
| FR-63 | Must | `cubit menubar` starts a macOS menu bar app: an icon at the top right of the menu bar that opens the menu above when clicked. It has no Dock icon. On other platforms the command says it is macOS only. |
| FR-64 | Must | Idle: the idle icon. Running: the running icon, plus a title next to it set by `menubar_title` in `config.yaml` (`none`, `time` or `project-time`; default `time`), for example `1:24`. |
| FR-65 | Must | **Start timer** is a submenu of active projects (most recently used first, at most 8). Each project opens a submenu with its categories in suggestion order (FR-46), "No category" and "New category...". Choosing an item starts the timer immediately. |
| FR-66 | Must | While a timer runs, the menu shows project, category and start time, plus **Stop timer** and **Cancel timer** (FR-4). Stop asks for an optional note in a small dialog, prefilled with the timer's note (FR-2). |
| FR-67 | Must | The menu shows today's and this week's totals as `H:MM`, refreshed whenever the menu opens. |
| FR-68 | Must | **Open dashboard** opens the web app in the default browser. If the web app is not answering on its port, the menu bar app first starts `cubit web` in the background. The web app exposes `/healthz` so the menu bar app can check that the process on that port is Cubit. A server the menu bar app started is stopped when it quits; one that was already running is left alone. |
| FR-69 | Must | **Quit Cubit** closes the menu bar app only. A running timer keeps running, because it lives in `.state/timer.json` (FR-8). |
| FR-70 | Must | State is shared: a change made in the CLI or web app shows up in the menu bar within 30 seconds, and immediately when the menu is opened. |
| FR-71 | Must | The menu bar app contains no business logic. It calls `cubit.core` for everything, and its menu contents (title, items, ordering, totals) are built by a pure function that can be tested without macOS. |
| FR-72 | Must | Icons are monochrome template images (black with transparency), so macOS adapts them to light and dark menu bars. They live in `design/menubar/`: idle and running PNGs (64x64 px, so they stay sharp on retina screens, loaded with `template=True`) and their SVG sources. Idle is an outlined cube; running is a solid cube. |
| FR-73 | Must | Errors never fail silently. If the data files are invalid or locked, the menu shows a "Data problem: run `cubit check`" item. Unexpected errors show a notification and are logged. |
| FR-74 | Should | Start at login: `cubit menubar install-login` writes a LaunchAgent (`no.icecubesol.cubit`) that starts the app at login, and `uninstall-login` removes it. Quitting from the menu does not relaunch it. |
| FR-75 | Should | Installation: `pipx install ".[menubar]"` puts `cubit` on the PATH. `rumps` is an optional extra, installed on macOS only. During development: `pip install -e ".[menubar]"`. |
| FR-76 | Could | **Add entry...** in the menu for a quick manual entry (project, duration, note) through dialogs. |
| FR-77 | Could | Notification when a timer has run longer than a configurable number of hours (default 8), to catch a forgotten timer. |

## 4. Data model and file formats

Default folder: `~/cubit-data`

```
cubit-data/
├── config.yaml
├── projects.yaml
├── entries/YYYY-MM.csv
└── .state/
    ├── timer.json
    └── secret_key
```

### 4.1 `entries/YYYY-MM.csv`

One file per month, chosen by the entry's date.

```csv
id,date,start,end,duration_minutes,project_id,category,note
a3f9c1,2026-09-18,09:05,10:35,90,acme-web,software-coding,Landing page layout
b71c02,2026-09-18,,,45,internal,,Invoicing and admin
c48d7e,2026-09-19,13:00,13:40,40,acme-web,project-management,Sprint planning call
```

| Column | Rules |
|---|---|
| `id` | 6 hex characters, unique across all files, generated by the app |
| `date` | `YYYY-MM-DD`, local date (start date for timers) |
| `start`, `end` | `HH:MM` local time on a 24-hour clock; both blank for manual entries without times |
| `duration_minutes` | Integer ≥ 1. **Source of truth for all totals.** |
| `project_id` | Must match a project in `projects.yaml` |
| `category` | Optional. Lowercase slug (`a-z`, `0-9`, `-`, max 40 characters) without the `#`. Blank means uncategorized. Should be registered on the project. |
| `note` | Free text, standard CSV quoting |

### 4.2 `projects.yaml`

```yaml
projects:
  - id: acme-web
    name: Acme website
    client: Acme Corp
    status: active            # active | archived
    categories:               # registered sub-categories, shown as #name
      - software-coding
      - project-management
    budget_hours: 120         # optional
    rates:                    # optional; empty = unrated / internal
      - valid_from: 2026-01-01
        rate: 95
      - valid_from: 2026-07-01
        rate: 105
```

Rates are hourly, in the currency from `config.yaml`. Money is handled as `Decimal`.

`categories` is a plain list you can edit by hand. The app appends to it when you use a new category (FR-45) and orders suggestions from your entry history (FR-46), so the list itself carries no counts.

### 4.3 `config.yaml`

```yaml
currency: NOK                 # default; any code works: NOK, EUR, USD, ...
week_starts_on: monday
budget_warning_percent: 80
prompt_for_category: true
theme: dark                   # dark | light | auto
menubar_title: time           # none | time | project-time (macOS menu bar)
```

`currency` is a label on the money, not a conversion: cubit never converts
between currencies (open question 4), and it cannot be blank. Times are 24-hour
everywhere -- stored, entered and displayed -- so there is no am/pm to get wrong.

The file is meant to be edited by hand, and the web app's settings page (FR-78)
edits the same six values through a form without disturbing the comments in it.

### 4.4 `.state/timer.json`

Exists only while a timer is running. Kept out of `entries/` and `projects.yaml` so it does not get synced or committed by accident.

```json
{"project_id": "acme-web", "started_at": "2026-09-18T09:05:12+02:00", "category": "software-coding", "note": "Landing page layout"}
```

`started_at` is timezone-aware, so elapsed time stays correct across DST changes. Stored entries use local `HH:MM`. `category` is the optional category the timer was started with (FR-1); it is `null` when the timer has none, and can still be changed at stop.

`.state/` also holds `cubit.lock`, the lock file writes are taken under (FR-39), and `secret_key`, which signs the web app's session cookie and therefore its CSRF tokens (FR-36). The key is 64 hex characters, generated on first use with `0600` permissions, and has to survive a restart or a form already open in the browser would stop working. Like `timer.json`, neither belongs to the data itself: they are kept out of `entries/` and `projects.yaml` so they are never synced or committed.

### 4.5 Theme tokens

Defined in `web/static/theme.css`, started from `design/theme.css`, and used by every template and stylesheet. Cubit's own palette, inspired by the IceCube Solutions site: near-black backgrounds and the site's cyan accent (dark, default), and an "ice" light variant built on the site's pale blue and link blues.

| Token | Dark (default) | Light (ice) | Use |
|---|---|---|---|
| `--color-bg` | `#060b10` | `#eaf6ff` | Page background |
| `--color-surface` | `#0d151d` | `#ffffff` | Cards, tables |
| `--color-surface-raised` | `#142029` | `#f4faff` | Inputs, hover rows |
| `--color-border` | `#1f2e3a` | `#cfe3f1` | Dividers, inputs |
| `--color-text` | `#e8f1f7` | `#0b2233` | Body text |
| `--color-text-muted` | `#8fa5b5` | `#4a6478` | Secondary text |
| `--color-accent` | `#00d4ff` | `#0077cc` | Buttons, links, active nav, category chips |
| `--color-accent-hover` | `#5fe3ff` | `#005f88` | Hover state |
| `--color-accent-contrast` | `#001a22` | `#ffffff` | Text on accent buttons |
| `--color-success` | `#3ddc97` | `#16855a` | On budget |
| `--color-warning` | `#ffb84d` | `#9a5b00` | Budget threshold reached |
| `--color-danger` | `#ff6b6b` | `#c62f3a` | Over budget, errors |
| `--font-body` | Inter, system-ui | | Text (JetBrains Sans is not bundled: see FR-58) |
| `--font-mono` | JetBrains Mono | | Navigation, durations, totals, ids, `#categories` (bundled) |
| `--radius-card` / `--radius-pill` | 12px / 999px | | Cards / chips and buttons |
| `--header-h` | 64px | | Frosted, fixed header |

Also defined in the file: translucent accent tints for chips and soft buttons, the header background, the background glow, card shadow and a spacing scale. Durations and totals use the mono font so columns line up.

**Logo:** `design/cubit-mark.svg`, an isometric ice cube whose top face is a clock showing 3:00. It doubles as the favicon. The header shows the mark followed by the word "cubit" in `--font-mono`. See `design/brand-preview.svg` for the result. The macOS menu bar uses separate monochrome versions of the mark (FR-72).

## 5. Non-functional requirements

- **Platforms:** core, CLI and web app run on Windows, macOS and Linux (Python 3.11+). The menu bar app is macOS only and optional.
- **Data safety:** no partial rows, no lost data on crashes or concurrent use (FR-39).
- **Privacy:** everything stays on the machine. No telemetry, no network calls.
- **Simplicity:** few dependencies; adding one needs a reason.
- **Performance:** instant for tens of thousands of entries. Reports read only the monthly files they need.
- **Testability:** core logic has no dependency on Typer or Flask and is unit-tested.
- **Time handling:** local time zone; DST and month/year boundaries covered by tests.

## 6. Architecture

```
CLI (Typer)        ─┐
Web (Flask)        ─┼─▶  core  ─▶  files (CSV / YAML / JSON)
Menu bar (rumps)   ─┘   (macOS only, optional)
```

- `core` holds models, storage, timer, rate lookup, duration parsing and reports.
- CLI and web are thin: parse input, call core, format output.
- All file access goes through `core.storage`.
- Reports are pure functions over entries and projects.

Planned layout:

```
src/cubit/
├── core/    # models, storage, timer, rates, durations, reports
├── cli/     # Typer app and commands
├── web/     # Flask app, templates/, static/ (theme.css, logo, fonts)
└── menubar/ # macOS menu bar app (rumps), optional; menu logic in a pure module
tests/
└── fixtures/
design/    # theme.css, logo, brand preview (used in M4) and menubar/ icons (used in M6)
```

## 7. Out of scope for v1

- Invoicing, PDF exports
- Multiple users, login, permissions
- Cloud sync (the file layout should not prevent it)
- Mobile app
- Billable/non-billable flag
- Free-form entry-level tags and multiple categories per entry
- Separate client records (contacts, addresses)
- Calendar integrations

## 8. Open questions

1. ~~**Web framework:**~~ **Resolved:** Flask, server-rendered, no JS build step (built in M4).
2. **Clients:** modelled as a `client` field on each project. Is a separate client record with its own settings ever needed?
3. **Time granularity:** whole minutes, timer rounds to the nearest minute. Should there be optional rounding (e.g. up to 15 min)?
4. **Currency:** one global currency in `config.yaml`, defaulting to `NOK`. It is a label, not a conversion. Is multi-currency needed?
5. **YAML library:** `ruamel.yaml` keeps your comments when the app rewrites `projects.yaml`; PyYAML would drop them.
6. **Default data folder:** `~/cubit-data` (visible, easy to back up). Prefer a hidden or OS-standard location?
7. **One category per entry:** keeps category totals clean. Several per entry would count the same hours twice in category reports.
8. **Palette and logo:** proposals, based on the site but Cubit's own (section 4.5 and `design/`). Adjust freely: only `theme.css` and the logo files change.
9. ~~**JetBrains Sans license:**~~ **Resolved:** only JetBrains Mono is bundled (SIL OFL). JetBrains Sans is not redistributed; body text uses Inter, then the system UI font. See FR-58.
10. **Menu bar library:** `rumps` (Python, same codebase) is proposed. A native Swift menu bar app could offer a richer popover, but it would be a second codebase.
11. **Menu bar title:** elapsed time only by default. `project-time` also shows the project but takes more menu bar space.

## 9. Milestones

| # | Milestone | Contents |
|---|---|---|
| M1 | Core | Models, storage, duration parsing, rate lookup, category registry and suggestion ranking, tests |
| M2 | CLI basics | `init`, projects, timer, manual entries with categories, list/edit/delete |
| M3 | Reports | Core report functions and CLI output (week, month, project, client) |
| M4 | Web app | Dashboard, entries, projects, reports, theme, CSRF |
| M5 | Polish | `cubit check`, docs, shell completion |
| M6 | macOS menu bar app | `cubit menubar` (rumps): icons, start/stop timer, totals, open dashboard, start at login. Needs M2 and M4 |
