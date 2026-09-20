# Cubit

A small time-logging tool for a one-person company. Log hours per project from the command line or a local web app, keep everything in plain-text files you can read and edit by hand, and get weekly, monthly, per-client and per-project summaries.

Built for IceCube Solutions.

> **Status: usable from the command line.** Logging time and reporting on it both work today: `init`, the timer, manual entries, categories, project management and the weekly, monthly, per-project, per-client and per-category summaries. The data-folder check (`cubit check`) and the web app (`cubit web`) are not built yet; they are milestones 4 and 5. See [REQUIREMENTS.md](REQUIREMENTS.md) for the full specification and the milestones.

## Features

- Start/stop timer **or** add time manually after the fact
- CLI (`cubit`) and local web app (`cubit web`, *planned*) on one shared core
- Projects with client, hourly-rate history, status (active/archived) and an hour budget
- Categories per project (e.g. `#software-coding`), remembered and suggested as you log, and totalled across projects
- Web app with its own IceCube-inspired look: dark by default, light "ice" theme available *(planned)*
- Reports: weekly, monthly, per project (hours vs. budget), per client, per category
- Plain-text storage: CSV for time entries, YAML for projects. No database
- Local-first; the data folder is laid out so syncing can be added later

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .

cubit init                         # creates the data folder
cubit project add acme-web --name "Acme website" --client "Acme Corp" --rate 95
cubit start acme-web -c software-coding -m "Landing page layout"
cubit stop
cubit add acme-web 1h30m -c project-management --date 2026-09-18 -m "Client call"
cubit list
cubit project show acme-web

cubit report week                  # this week, by project and by day
cubit report month last            # last month, by project, client and week
cubit report project acme-web      # hours vs. budget, earnings, categories

cubit web                          # planned, milestone 4
```

## CLI overview

| Command | Purpose |
|---|---|
| `cubit init` | Create the data folder and config |
| `cubit start <project> [-c category] [-m note]` | Start the timer |
| `cubit stop [-c category] [-m note]` | Stop the timer and save an entry |
| `cubit status` | Show the running timer |
| `cubit cancel` | Drop the running timer without logging |
| `cubit add <project> <duration> [-c category] [--date D] [-m note]` | Add an entry manually |
| `cubit list [filters]` | List entries |
| `cubit edit <id>` / `cubit rm <id>` | Change or delete an entry |
| `cubit project add\|list\|show\|edit\|rate\|archive\|unarchive\|rm\|category` | Manage projects, rates and categories |
| `cubit report week\|month\|project\|client\|category` | Summaries |
| `cubit check` | Validate the data folder *(milestone 5)* |
| `cubit web` | Start the local web app *(milestone 4)* |

Durations accept `90m`, `1h30m`, `1.5h` and `1:30`. Dates accept `YYYY-MM-DD`,
`today` and `yesterday`.

`cubit list` shows the current month by default; `--all` shows everything, and
`--from` / `--to` / `--project` / `--client` / `--category` narrow it down.
Every command takes `--data-dir`, and `--yes` skips the prompts for scripts.

### Reports

`cubit report week` and `cubit report month` take `this` (the default), `last`,
a date inside the period, or a name like `2026-W39` or `2026-09`. Every report
accepts `--from` / `--to` for a custom range and `-c` to narrow to one category;
`--by-category` breaks each project down as well.

Weeks are ISO weeks (Monday to Sunday) unless `week_starts_on: sunday` says
otherwise. A project's budget is measured against every hour ever logged against
it, not just the hours in the report, and warns at `budget_warning_percent`
(default 80%) and again once it is exceeded. Time that no rate covers is counted
in its own column as *unrated* rather than as zero earnings.

### Categories

Each project has its own sub-categories, such as `#project-management` or `#software-coding`. Add one with `-c` when you log time. Cubit registers new categories on that project and suggests the ones you've used before, most recent first. The same name can be used in several projects, so you can also see all `#project-management` time across everything.

When you use a category the project has not seen before, cubit asks once
before registering it, and offers the closest existing name if it looks like a
typo. Leave `-c` off and it lists the project's categories to pick from; turn
that off with `prompt_for_category: false` in `config.yaml`.

> Write `-c software-coding` without the `#`. In shells like bash and PowerShell an unquoted `#` starts a comment. `-c "#software-coding"` also works.

## Data

Everything lives in one folder (default `~/cubit-data`, override with `--data-dir` or `CUBIT_DATA_DIR`):

```
cubit-data/
├── config.yaml          # currency, week start, budget warning level, theme
├── projects.yaml        # clients/projects, rates, status, categories, budgets
├── entries/
│   ├── 2026-08.csv      # one file per month
│   └── 2026-09.csv
└── .state/
    └── timer.json       # the currently running timer (not for syncing)
```

Example entry file (`entries/2026-09.csv`):

```csv
id,date,start,end,duration_minutes,project_id,category,note
a3f9c1,2026-09-18,09:05,10:35,90,acme-web,software-coding,Landing page layout
b71c02,2026-09-18,,,45,internal,,Invoicing and admin
c48d7e,2026-09-19,13:00,13:40,40,acme-web,project-management,Sprint planning call
```

Example project (`projects.yaml`):

```yaml
projects:
  - id: acme-web
    name: Acme website
    client: Acme Corp
    status: active            # active | archived
    categories:               # shown as #software-coding etc.
      - software-coding
      - project-management
    budget_hours: 120
    rates:
      - valid_from: 2026-01-01
        rate: 95
      - valid_from: 2026-07-01
        rate: 105
```

You can edit these files by hand. Cubit validates them on load and tells you which file and row is wrong.

## Development

- Stack: Python 3.11+, Typer, Flask, Pydantic, ruamel.yaml, filelock, pytest, ruff
- Architecture and contribution rules: [AGENT.md](AGENT.md)
- Requirements, data model and milestones: [REQUIREMENTS.md](REQUIREMENTS.md)
- Logo, theme tokens and brand preview: [design/](design/)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pip install -e .

pytest
ruff check . && ruff format .
```

The code is laid out `src/cubit/{core,cli,web}`. All business logic lives in
`cubit.core`, which never imports Typer or Flask, and every read and write of a
data file goes through `cubit.core.storage`.

## License

MIT. See [LICENSE](LICENSE).
