"""Timer and entry commands: start, stop, status, cancel, add, list, edit, rm.

Thin by design: parse the options, call ``cubit.core``, print the result.
"""

from __future__ import annotations

from datetime import date

import typer

from cubit.cli.context import get_context
from cubit.cli.output import (
    ENTRY_COLUMNS,
    accent,
    echo,
    entry_rows,
    format_date,
    format_duration,
    format_total,
    muted,
    table,
)
from cubit.cli.parsing import parse_clock, parse_day, parse_minutes
from cubit.cli.prompts import choose_category, confirm_category
from cubit.core import (
    UNSET,
    add_manual_entry,
    cancel_timer,
    display_category,
    edit_entry,
    elapsed_minutes,
    find_entries,
    remove_entry,
    running_timer,
    start_timer,
    stop_timer,
    suggest_categories,
)

CATEGORY_HELP = "Category for this entry, without the # (quote it if you write one)."


def register(app: typer.Typer) -> None:
    """Add the timer and entry commands to ``app``."""
    app.command("start")(start)
    app.command("stop")(stop)
    app.command("status")(status)
    app.command("cancel")(cancel)
    app.command("add")(add)
    app.command("list")(list_entries)
    app.command("edit")(edit)
    app.command("rm")(remove)


def _resolve_category(
    ctx: typer.Context,
    project_id: str,
    category: str | None,
    *,
    yes: bool,
) -> str | None:
    """Settle on the category to use, asking only when it helps."""
    # FR-45, FR-53.
    app_ctx = get_context(ctx)
    storage = app_ctx.require_folder()
    project = storage.get_project(project_id)

    if category:
        return confirm_category(project, category, assume_yes=yes)

    if yes:
        return None
    return choose_category(
        project,
        suggest_categories(project, storage.load_all_entries()),
        enabled=app_ctx.config().prompt_for_category,
    )


def start(
    ctx: typer.Context,
    project: str = typer.Argument(..., help="Project id to log against."),
    category: str | None = typer.Option(None, "--category", "-c", help=CATEGORY_HELP),
    note: str = typer.Option("", "--message", "-m", help="What you are working on."),
    force: bool = typer.Option(False, "--force", help="Allow an archived project."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip every prompt."),
) -> None:
    """Start the timer for a project."""
    # FR-1.
    storage = get_context(ctx).require_folder()
    slug = _resolve_category(ctx, project, category, yes=yes)

    state = start_timer(storage, project, category=slug, note=note, force=force)
    started = state.started_at.astimezone().strftime("%H:%M")
    echo(f"Started {accent(state.project_id)} at {started} {display_category(state.category)}")
    if state.note:
        echo(muted(f"  {state.note}"))


def stop(
    ctx: typer.Context,
    note: str | None = typer.Option(None, "--message", "-m", help="Set or change the note."),
    category: str | None = typer.Option(None, "--category", "-c", help=CATEGORY_HELP),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip every prompt."),
) -> None:
    """Stop the timer and save the entry."""
    # FR-2.
    storage = get_context(ctx).require_folder()
    state = running_timer(storage)
    slug = None
    if state is not None and category:
        slug = confirm_category(storage.get_project(state.project_id), category, assume_yes=yes)

    entry = stop_timer(storage, note=note, category=slug)
    echo(
        f"Logged {accent(format_duration(entry.duration_minutes))} "
        f"to {entry.project_id} on {format_date(entry.date)} "
        f"{display_category(entry.category)}  [{entry.id}]"
    )
    if entry.note:
        echo(muted(f"  {entry.note}"))


def status(ctx: typer.Context) -> None:
    """Show the running timer."""
    # FR-3.
    storage = get_context(ctx).require_folder()
    state = running_timer(storage)
    if state is None:
        echo("No timer running.")
        raise typer.Exit()

    running = format_duration(elapsed_minutes(state))
    started = state.started_at.astimezone().strftime("%H:%M")
    echo(f"{accent(running)} on {state.project_id} {display_category(state.category)}")
    echo(muted(f"  started {started}"))
    if state.note:
        echo(muted(f"  {state.note}"))


def cancel(ctx: typer.Context) -> None:
    """Drop the running timer without logging anything."""
    # FR-4.
    storage = get_context(ctx).require_folder()
    state = cancel_timer(storage)
    echo(f"Cancelled the timer on {state.project_id}. Nothing was logged.")


def add(
    ctx: typer.Context,
    project: str = typer.Argument(..., help="Project id to log against."),
    duration: str = typer.Argument(..., help="How long, e.g. 90m, 1h30m, 1.5h or 1:30."),
    category: str | None = typer.Option(None, "--category", "-c", help=CATEGORY_HELP),
    note: str = typer.Option("", "--message", "-m", help="What the time was spent on."),
    day: str | None = typer.Option(None, "--date", help="Date (YYYY-MM-DD). Default today."),
    start_at: str | None = typer.Option(None, "--start", help="Start time (HH:MM), optional."),
    force: bool = typer.Option(False, "--force", help="Allow an archived project."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip every prompt."),
) -> None:
    """Add an entry by hand."""
    # FR-5.
    storage = get_context(ctx).require_folder()
    minutes = parse_minutes(duration)
    when = parse_day(day) or date.today()
    slug = _resolve_category(ctx, project, category, yes=yes)

    entry = add_manual_entry(
        storage,
        project,
        minutes,
        day=when,
        category=slug,
        note=note,
        start=parse_clock(start_at),
        force=force,
    )
    echo(
        f"Logged {accent(format_duration(entry.duration_minutes))} "
        f"to {entry.project_id} on {format_date(entry.date)} "
        f"{display_category(entry.category)}  [{entry.id}]"
    )


def list_entries(
    ctx: typer.Context,
    since: str | None = typer.Option(None, "--from", help="First date (YYYY-MM-DD)."),
    until: str | None = typer.Option(None, "--to", help="Last date (YYYY-MM-DD)."),
    project: str | None = typer.Option(None, "--project", "-p", help="Only this project id."),
    client: str | None = typer.Option(None, "--client", help="Only this client's projects."),
    category: str | None = typer.Option(None, "--category", "-c", help="Only this category."),
    show_all: bool = typer.Option(False, "--all", help="Every entry, not just this month."),
    limit: int | None = typer.Option(None, "--limit", help="Show at most this many."),
) -> None:
    """List entries, with filters."""
    # FR-6.
    storage = get_context(ctx).require_folder()
    start = parse_day(since)
    end = parse_day(until)

    if start is None and end is None and not show_all:
        # A useful default: this month, which is one file to read.
        today = date.today()
        start = today.replace(day=1)
        end = today

    entries = find_entries(
        storage,
        start=start,
        end=end,
        project_id=project,
        client=client,
        category=category,
    )
    if limit is not None:
        entries = entries[-limit:]

    if not entries:
        echo("No entries found.")
        raise typer.Exit()

    projects = storage.load_projects_map()
    echo(table(ENTRY_COLUMNS, entry_rows(entries, projects)))
    total = sum(entry.duration_minutes for entry in entries)
    counted = "1 entry" if len(entries) == 1 else f"{len(entries)} entries"
    echo()
    echo(f"{counted}, {accent(format_total(total))}")
    if start or end:
        echo(
            muted(
                f"  {format_date(start) if start else '...'} to "
                f"{format_date(end) if end else '...'}"
            )
        )


def edit(
    ctx: typer.Context,
    entry_id: str = typer.Argument(..., help="Id of the entry to change."),
    duration: str | None = typer.Option(None, "--duration", "-d", help="New duration."),
    day: str | None = typer.Option(None, "--date", help="New date (YYYY-MM-DD)."),
    project: str | None = typer.Option(None, "--project", "-p", help="Move to this project."),
    category: str | None = typer.Option(None, "--category", "-c", help=CATEGORY_HELP),
    clear_category: bool = typer.Option(False, "--no-category", help="Remove the category."),
    note: str | None = typer.Option(None, "--message", "-m", help="New note."),
    start_at: str | None = typer.Option(None, "--start", help="New start time (HH:MM)."),
    clear_times: bool = typer.Option(False, "--no-times", help="Remove start and end."),
    force: bool = typer.Option(False, "--force", help="Allow an archived project."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip every prompt."),
) -> None:
    """Change an entry by its id."""
    # FR-7.
    storage = get_context(ctx).require_folder()
    if clear_category and category:
        raise typer.BadParameter("Use either --category or --no-category, not both.")
    if clear_times and start_at:
        raise typer.BadParameter("Use either --start or --no-times, not both.")

    existing = storage.find_entry(entry_id)
    target_project = project or (existing.project_id if existing else None)

    new_category: object = UNSET
    if clear_category:
        new_category = None
    elif category and target_project:
        new_category = confirm_category(
            storage.get_project(target_project), category, assume_yes=yes
        )

    new_start: object = UNSET
    if clear_times:
        new_start = None
    elif start_at:
        new_start = parse_clock(start_at)

    entry = edit_entry(
        storage,
        entry_id,
        day=parse_day(day) if day else UNSET,
        duration_minutes=parse_minutes(duration) if duration else UNSET,
        project_id=project if project else UNSET,
        category=new_category,
        note=note if note is not None else UNSET,
        start=new_start,
        force=force,
    )
    echo(
        f"Updated {accent(entry.id)}: {format_date(entry.date)} "
        f"{format_duration(entry.duration_minutes)} {entry.project_id} "
        f"{display_category(entry.category)}"
    )


def remove(
    ctx: typer.Context,
    entry_id: str = typer.Argument(..., help="Id of the entry to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask."),
) -> None:
    """Delete an entry by its id."""
    # FR-7.
    storage = get_context(ctx).require_folder()
    entry = storage.find_entry(entry_id)
    if entry is not None and not yes:
        rows = entry_rows([entry], storage.load_projects_map())
        echo(table(ENTRY_COLUMNS, rows))
        typer.confirm("Delete this entry?", default=False, abort=True)

    deleted = remove_entry(storage, entry_id)
    echo(f"Deleted {deleted.id} ({format_duration(deleted.duration_minutes)}).")
