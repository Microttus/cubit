# Cubit

A small time-logging tool for a one-person company. Log hours per project from the command line or a local web app, keep everything in plain-text files you can read and edit by hand, and get weekly, monthly, per-client and per-project summaries.

Built for IceCube Solutions.

> **Status: early.** The core is built and tested -- models, plain-text storage with atomic locked writes, duration parsing, rate history and categories. The CLI is still only `cubit --version`, and the web app is not started. Everything marked *(planned)* below describes the intended behaviour, not what runs today. See [REQUIREMENTS.md](REQUIREMENTS.md) for the full specification and the milestones.

## Features (planned)

- Start/stop timer **or** add time manually after the fact
- CLI (`cubit`) and local web app (`cubit web`) on one shared core
- Projects with client, hourly-rate history, status (active/archived) and an hour budget
- Categories per project (e.g. `#software-coding`), remembered and suggested as you log, and totalled across projects
- Web app with its own IceCube-inspired look: dark by default, light "ice" theme available
- Reports: weekly, monthly, per project (hours vs. budget), per client
- Plain-text storage: CSV for time entries, YAML for projects. No database
- Local-first; the data folder is laid out so syncing can be added later

## Quick start (planned)

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
cubit report week
cubit web                          # opens http://127.0.0.1:8000
```

## CLI overview (planned)

| Command | Purpose |
|---|---|
| `cubit init` | Create the data folder and config |
| `cubit start <project> [-c category] [-m note]` | Start the timer |
| `cubit stop [-m note]` | Stop the timer and save an entry |
| `cubit status` | Show the running timer |
| `cubit add <project> <duration> [-c category] [--date D] [-m note]` | Add an entry manually |
| `cubit list [filters]` | List entries |
| `cubit edit <id>` / `cubit rm <id>` | Change or delete an entry |
| `cubit project add\|list\|show\|edit\|archive\|rate\|category` | Manage projects, rates and categories |
| `cubit report week\|month\|project\|client\|category` | Summaries |
| `cubit check` | Validate the data folder |
| `cubit web` | Start the local web app |

Durations accept `90m`, `1h30m`, `1.5h` and `1:30`.

### Categories

Each project has its own sub-categories, such as `#project-management` or `#software-coding`. Add one with `-c` when you log time. Cubit registers new categories on that project and suggests the ones you've used before, most recent first. The same name can be used in several projects, so you can also see all `#project-management` time across everything.

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
