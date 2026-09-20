"""Report commands: week, month, project, client and category.

All the arithmetic is in :mod:`cubit.core.reports`; this module chooses the
period, asks for the summary and lays it out.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import typer

from cubit.cli.completion import (
    complete_any_project,
    complete_category,
    complete_client,
    complete_format,
)
from cubit.cli.context import get_context
from cubit.cli.output import (
    ENTRY_COLUMNS,
    breakdown_table,
    budget_line,
    echo,
    entry_rows,
    format_duration,
    format_earnings,
    heading,
    muted,
    table,
)
from cubit.cli.parsing import parse_day
from cubit.core import (
    FORMATS,
    Config,
    CubitError,
    Document,
    Storage,
    Summary,
    category_document,
    category_report,
    client_document,
    client_report,
    display_category,
    find_entries,
    normalize_category,
    project_document,
    project_report,
    render,
    resolve_period,
    summarize,
    summary_document,
)

app = typer.Typer(
    help="Weekly, monthly, per-project and per-client summaries.", no_args_is_help=True
)

FORMAT_HELP = f"Write the report as one of {', '.join(FORMATS)} instead of a table."
OUTPUT_HELP = "Write to this file instead of the terminal."
RANGE_HELP_FROM = "Override the period: first date (YYYY-MM-DD)."
RANGE_HELP_TO = "Override the period: last date (YYYY-MM-DD)."
CATEGORY_HELP = "Only this category, without the #."


def _load(ctx: typer.Context) -> tuple[Storage, Config]:
    storage = get_context(ctx).require_folder()
    return storage, storage.load_config()


def _export(document: Document, fmt: str, output: str | None) -> bool:
    """Write the report out in another format, if one was asked for (FR-23).

    Returns True when it handled the output, so the caller skips the tables.
    """
    if fmt == "text":
        return False

    text = render(document, fmt)
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        echo(muted(f"Wrote {path}"))
    else:
        typer.echo(text, nl=False)
    return True


def _custom_range(since: str | None, until: str | None) -> tuple[date, date] | None:
    """The range from --from/--to, when either was given (FR-21)."""
    start = parse_day(since)
    end = parse_day(until)
    if start is None and end is None:
        return None
    if start is None or end is None:
        raise CubitError(
            "A custom range needs both ends.",
            hint="Pass --from and --to together.",
        )
    if start > end:
        raise CubitError(f"--from {start} is after --to {end}.")
    return start, end


def _period_header(title: str, start: date, end: date, total_line: str) -> None:
    echo(heading(f"{title}  {start.isoformat()} to {end.isoformat()}"))
    echo(total_line)
    echo()


def _totals(summary: Summary, currency: str) -> str:
    return (
        f"{format_duration(summary.total.minutes)} "
        f"({summary.total.hours} h)  ·  {format_earnings(summary.total, currency)}"
    )


def _section(title: str, lines, currency: str, *, skip_empty: bool = True) -> None:
    if skip_empty and not any(line.amount.minutes for line in lines):
        return
    rendered = breakdown_table(lines, title, currency)
    if rendered:
        echo(rendered)
        echo()


def _all_unrated_before_the_first_rate(report) -> bool:
    """True when every minute shown predates the project's first rate (FR-15).

    Unrated time has two very different causes -- no rate at all, or a rate that
    had not started yet -- and only the second one is worth explaining.
    """
    return bool(
        report.period.minutes
        and not report.period.has_earnings
        and report.project.rates
        and all(entry.date < report.project.rates[0].valid_from for entry in report.entries)
    )


def _project_categories(summary: Summary, storage: Storage, currency: str) -> None:
    """Each project broken down by category (FR-54)."""
    projects = storage.load_projects_map()
    for line in summary.by_project:
        breakdown = summary.by_project_category.get(line.key, [])
        if not breakdown:
            continue
        project = projects.get(line.key)
        echo(muted(f"{project.name if project else line.key}"))
        echo(breakdown_table(breakdown, "CATEGORY", currency))
        echo()


@app.command("week")
def week(
    ctx: typer.Context,
    when: str = typer.Argument(
        "this", help="'this', 'last', a date inside the week, or a week like 2026-W39."
    ),
    since: str | None = typer.Option(None, "--from", help=RANGE_HELP_FROM),
    until: str | None = typer.Option(None, "--to", help=RANGE_HELP_TO),
    category: str | None = typer.Option(
        None, "--category", "-c", help=CATEGORY_HELP, autocompletion=complete_category
    ),
    by_category: bool = typer.Option(
        False, "--by-category", help="Also break each project down by category."
    ),
    fmt: str = typer.Option(
        "text", "--format", "-f", help=FORMAT_HELP, autocompletion=complete_format
    ),
    output: str | None = typer.Option(None, "--output", "-o", help=OUTPUT_HELP),
) -> None:
    """Weekly summary: hours by project and by day."""
    # FR-17, FR-21, FR-54, FR-60.
    storage, config = _load(ctx)
    custom = _custom_range(since, until)
    start, end = custom or resolve_period("week", when, week_starts_on=config.week_starts_on)

    summary = summarize(
        find_entries(storage, start=start, end=end, category=category),
        storage.load_projects_map(),
        start=start,
        end=end,
        week_starts_on=config.week_starts_on,
        fill_days=True,
    )

    title = "Custom range" if custom else f"Week {start.isocalendar().week}, {start.year}"
    if _export(
        summary_document(summary, kind="week", label=title, currency=config.currency),
        fmt,
        output,
    ):
        return

    _period_header(title, start, end, _totals(summary, config.currency))
    if category:
        echo(muted(f"filtered to {display_category(normalize_category(category))}"))
        echo()

    _section("PROJECT", summary.by_project, config.currency)
    _section("DAY", summary.by_day, config.currency, skip_empty=False)
    _section("CATEGORY", summary.by_category, config.currency)
    if by_category:
        _project_categories(summary, storage, config.currency)


@app.command("month")
def month(
    ctx: typer.Context,
    when: str = typer.Argument(
        "this", help="'this', 'last', a date inside the month, or a month like 2026-09."
    ),
    since: str | None = typer.Option(None, "--from", help=RANGE_HELP_FROM),
    until: str | None = typer.Option(None, "--to", help=RANGE_HELP_TO),
    category: str | None = typer.Option(
        None, "--category", "-c", help=CATEGORY_HELP, autocompletion=complete_category
    ),
    by_category: bool = typer.Option(
        False, "--by-category", help="Also break each project down by category."
    ),
    fmt: str = typer.Option(
        "text", "--format", "-f", help=FORMAT_HELP, autocompletion=complete_format
    ),
    output: str | None = typer.Option(None, "--output", "-o", help=OUTPUT_HELP),
) -> None:
    """Monthly summary: hours by project, client and week."""
    # FR-18, FR-21, FR-54, FR-60.
    storage, config = _load(ctx)
    custom = _custom_range(since, until)
    start, end = custom or resolve_period("month", when, week_starts_on=config.week_starts_on)

    summary = summarize(
        find_entries(storage, start=start, end=end, category=category),
        storage.load_projects_map(),
        start=start,
        end=end,
        week_starts_on=config.week_starts_on,
    )

    title = "Custom range" if custom else start.strftime("%B %Y")
    if _export(
        summary_document(summary, kind="month", label=title, currency=config.currency),
        fmt,
        output,
    ):
        return

    _period_header(title, start, end, _totals(summary, config.currency))
    if category:
        echo(muted(f"filtered to {display_category(normalize_category(category))}"))
        echo()

    _section("PROJECT", summary.by_project, config.currency)
    _section("CLIENT", summary.by_client, config.currency)
    _section("WEEK", summary.by_week, config.currency, skip_empty=False)
    _section("CATEGORY", summary.by_category, config.currency)
    if by_category:
        _project_categories(summary, storage, config.currency)


@app.command("project")
def project(
    ctx: typer.Context,
    project_id: str = typer.Argument(..., help="Project id.", autocompletion=complete_any_project),
    since: str | None = typer.Option(None, "--from", help="First date (YYYY-MM-DD)."),
    until: str | None = typer.Option(None, "--to", help="Last date (YYYY-MM-DD)."),
    category: str | None = typer.Option(
        None, "--category", "-c", help=CATEGORY_HELP, autocompletion=complete_category
    ),
    entries: bool = typer.Option(False, "--entries", help="Also list the entries."),
    fmt: str = typer.Option(
        "text", "--format", "-f", help=FORMAT_HELP, autocompletion=complete_format
    ),
    output: str | None = typer.Option(None, "--output", "-o", help=OUTPUT_HELP),
) -> None:
    """One project: hours, budget, earnings and categories."""
    # FR-19, FR-21, FR-22, FR-49.
    storage, config = _load(ctx)
    start = parse_day(since)
    end = parse_day(until)
    target = storage.get_project(project_id)

    # The whole history, not just the period: FR-19 wants the project's total
    # hours beside the period's, and the budget covers every hour ever logged.
    report = project_report(
        target,
        find_entries(storage, category=category),
        storage.load_projects_map(),
        start=start,
        end=end,
        warning_percent=config.budget_warning_percent,
    )

    if _export(
        project_document(
            report,
            currency=config.currency,
            projects=storage.load_projects_map(),
            entries=entries,
        ),
        fmt,
        output,
    ):
        return

    echo(heading(f"{target.id}  {target.name}"))
    if target.client:
        echo(f"  client    {target.client}")
    echo(f"  total     {format_duration(report.total.minutes)} ({report.total.hours} h)")
    if start or end:
        echo(
            f"  period    {format_duration(report.period.minutes)} "
            f"({report.period.hours} h)  "
            f"{start.isoformat() if start else '...'} to {end.isoformat() if end else '...'}"
        )
    echo(f"  earned    {format_earnings(report.period, config.currency)}")
    if _all_unrated_before_the_first_rate(report):
        first = report.project.rates[0].valid_from
        echo(muted(f"            no rate applied yet: the first one starts {first}"))
    if report.budget is not None:
        echo(f"  budget    {budget_line(report.budget)}")
    else:
        echo(muted("  budget    none set"))
    echo()

    _section("CATEGORY", report.by_category, config.currency)

    if entries:
        if not report.entries:
            echo("No entries in this period.")
            return
        echo(table(ENTRY_COLUMNS, entry_rows(report.entries, storage.load_projects_map())))


@app.command("client")
def client(
    ctx: typer.Context,
    name: str = typer.Argument(
        ..., help="Client name, as written on the projects.", autocompletion=complete_client
    ),
    since: str | None = typer.Option(None, "--from", help="First date (YYYY-MM-DD)."),
    until: str | None = typer.Option(None, "--to", help="Last date (YYYY-MM-DD)."),
    category: str | None = typer.Option(
        None, "--category", "-c", help=CATEGORY_HELP, autocompletion=complete_category
    ),
    fmt: str = typer.Option(
        "text", "--format", "-f", help=FORMAT_HELP, autocompletion=complete_format
    ),
    output: str | None = typer.Option(None, "--output", "-o", help=OUTPUT_HELP),
) -> None:
    """One client: hours and earnings across their projects."""
    # FR-20, FR-21.
    storage, config = _load(ctx)
    start = parse_day(since)
    end = parse_day(until)

    report = client_report(
        name,
        find_entries(storage, category=category),
        storage.load_projects_map(),
        start=start,
        end=end,
    )
    if not report.projects:
        raise CubitError(
            f"No projects for client {name!r}.",
            hint="Run 'cubit project list --all' to see the clients you have.",
        )

    if _export(client_document(report, currency=config.currency), fmt, output):
        return

    echo(heading(report.client))
    echo(
        f"{format_duration(report.total.minutes)} ({report.total.hours} h)"
        f"  ·  {format_earnings(report.total, config.currency)}"
    )
    echo(muted(f"  {len(report.projects)} projects"))
    echo()
    _section("PROJECT", report.by_project, config.currency)


@app.command("category")
def category(
    ctx: typer.Context,
    name: str = typer.Argument(
        ..., help="Category name, without the #.", autocompletion=complete_category
    ),
    since: str | None = typer.Option(None, "--from", help="First date (YYYY-MM-DD)."),
    until: str | None = typer.Option(None, "--to", help="Last date (YYYY-MM-DD)."),
    fmt: str = typer.Option(
        "text", "--format", "-f", help=FORMAT_HELP, autocompletion=complete_format
    ),
    output: str | None = typer.Option(None, "--output", "-o", help=OUTPUT_HELP),
) -> None:
    """One category across every project that uses it."""
    # FR-60, FR-61.
    storage, config = _load(ctx)
    start = parse_day(since)
    end = parse_day(until)

    report = category_report(
        name,
        find_entries(storage),
        storage.load_projects_map(),
        start=start,
        end=end,
    )

    if _export(category_document(report, currency=config.currency), fmt, output):
        return

    echo(heading(display_category(report.category)))
    if not report.entries:
        echo("Nothing logged to that category.")
        return

    echo(
        f"{format_duration(report.total.minutes)} ({report.total.hours} h)"
        f"  ·  {format_earnings(report.total, config.currency)}"
    )
    echo()
    _section("PROJECT", report.by_project, config.currency)
