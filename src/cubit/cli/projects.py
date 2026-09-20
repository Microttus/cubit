"""Project commands: add, list, show, edit, archive, unarchive, rate, category."""

from __future__ import annotations

from datetime import date

import typer

from cubit.cli.context import get_context
from cubit.cli.output import (
    Column,
    accent,
    echo,
    format_date,
    format_total,
    muted,
    table,
)
from cubit.cli.parsing import parse_day, parse_hours, parse_money
from cubit.core import (
    UNSET,
    archive_project,
    create_project,
    display_category,
    edit_project,
    format_duration,
    normalize_category,
    rate_for_date,
    register_project_category,
    remove_project,
    set_rate,
    suggest_categories,
    unarchive_project,
    unregister_project_category,
)

app = typer.Typer(help="Create and manage projects, rates and categories.", no_args_is_help=True)
category_app = typer.Typer(help="Registered categories of a project.", no_args_is_help=True)
app.add_typer(category_app, name="category")

PROJECT_COLUMNS = (
    Column("ID"),
    Column("NAME"),
    Column("CLIENT"),
    Column("STATUS"),
    Column("RATE", "right"),
    Column("BUDGET", "right"),
    Column("LOGGED", "right"),
)


@app.command("add")
def add(
    ctx: typer.Context,
    project_id: str = typer.Argument(..., help="Short lowercase id, e.g. acme-web."),
    name: str = typer.Option(..., "--name", "-n", help="Human-readable project name."),
    client: str = typer.Option("", "--client", help="Client this project belongs to."),
    rate: str | None = typer.Option(None, "--rate", help="Hourly rate to start from."),
    rate_from: str | None = typer.Option(None, "--rate-from", help="Date the rate starts."),
    budget: str | None = typer.Option(None, "--budget", help="Hour budget, e.g. 120."),
    categories: list[str] = typer.Option(
        [], "--category", "-c", help="Register a category up front. Repeatable."
    ),
) -> None:
    """Create a project."""
    # FR-11.
    storage = get_context(ctx).require_folder()
    project = create_project(
        storage,
        project_id,
        name=name,
        client=client,
        budget_hours=parse_hours(budget),
        categories=categories,
        rate=parse_money(rate),
        rate_from=parse_day(rate_from),
    )
    echo(f"Created {accent(project.id)} ({project.name}).")


@app.command("list")
def list_projects(
    ctx: typer.Context,
    show_all: bool = typer.Option(False, "--all", "-a", help="Include archived projects."),
    client: str | None = typer.Option(None, "--client", help="Only this client's projects."),
) -> None:
    """List projects. Archived ones are hidden unless you ask."""
    # FR-13.
    storage = get_context(ctx).require_folder()
    projects = storage.load_projects()
    if not show_all:
        projects = [project for project in projects if project.is_active]
    if client:
        projects = [p for p in projects if p.client.casefold() == client.casefold()]

    if not projects:
        echo("No projects yet." if not client else "No projects for that client.")
        raise typer.Exit()

    logged: dict[str, int] = {}
    for entry in storage.load_all_entries():
        logged[entry.project_id] = logged.get(entry.project_id, 0) + entry.duration_minutes

    today = date.today()
    rows = []
    for project in projects:
        rate = rate_for_date(project, today)
        rows.append(
            [
                project.id,
                project.name,
                project.client,
                project.status.value,
                f"{rate}" if rate is not None else "-",
                f"{project.budget_hours}" if project.budget_hours is not None else "-",
                format_duration(logged.get(project.id, 0)),
            ]
        )
    echo(table(PROJECT_COLUMNS, rows))


@app.command("show")
def show(
    ctx: typer.Context,
    project_id: str = typer.Argument(..., help="Project id."),
) -> None:
    """Show one project with its rate history and categories."""
    # FR-11.
    storage = get_context(ctx).require_folder()
    project = storage.get_project(project_id)
    entries = storage.load_entries(project_id=project.id)
    total = sum(entry.duration_minutes for entry in entries)

    echo(f"{accent(project.id)}  {project.name}")
    if project.client:
        echo(f"  client    {project.client}")
    echo(f"  status    {project.status.value}")
    echo(f"  logged    {format_total(total)} over {len(entries)} entries")
    if project.budget_hours is not None:
        echo(f"  budget    {project.budget_hours} h")

    if project.rates:
        echo("  rates")
        for step in project.rates:
            echo(f"    from {format_date(step.valid_from)}  {step.rate}")
    else:
        echo(muted("  rates     none (time on this project is unrated)"))

    if project.categories:
        echo("  categories")
        echo(f"    {'  '.join(display_category(name) for name in project.categories)}")
    else:
        echo(muted("  categories none registered yet"))


@app.command("edit")
def edit(
    ctx: typer.Context,
    project_id: str = typer.Argument(..., help="Project id. The id itself cannot change."),
    name: str | None = typer.Option(None, "--name", "-n", help="New name."),
    client: str | None = typer.Option(None, "--client", help="New client."),
    budget: str | None = typer.Option(None, "--budget", help="New hour budget."),
    clear_budget: bool = typer.Option(False, "--no-budget", help="Remove the hour budget."),
) -> None:
    """Change a project's details."""
    # FR-11, FR-12.
    storage = get_context(ctx).require_folder()
    if clear_budget and budget:
        raise typer.BadParameter("Use either --budget or --no-budget, not both.")

    new_budget: object = UNSET
    if clear_budget:
        new_budget = None
    elif budget:
        new_budget = parse_hours(budget)

    project = edit_project(
        storage,
        project_id,
        name=name if name is not None else UNSET,
        client=client if client is not None else UNSET,
        budget_hours=new_budget,
    )
    echo(f"Updated {accent(project.id)}.")


@app.command("rate")
def rate(
    ctx: typer.Context,
    project_id: str = typer.Argument(..., help="Project id."),
    amount: str = typer.Argument(..., help="Hourly rate, e.g. 105 or 105.50."),
    valid_from: str | None = typer.Option(
        None, "--from", help="Date the rate starts. Default today."
    ),
) -> None:
    """Add a step to the project's rate history."""
    # FR-14.
    storage = get_context(ctx).require_folder()
    money = parse_money(amount)
    assert money is not None  # a required argument always parses to a value
    project = set_rate(storage, project_id, money, parse_day(valid_from))
    latest = project.rates[-1]
    echo(f"{accent(project.id)} is {latest.rate} an hour from {format_date(latest.valid_from)}.")


@app.command("archive")
def archive(
    ctx: typer.Context,
    project_id: str = typer.Argument(..., help="Project id."),
) -> None:
    """Archive a project, keeping its entries."""
    # FR-13.
    storage = get_context(ctx).require_folder()
    project = archive_project(storage, project_id)
    echo(f"Archived {accent(project.id)}. Its entries and reports are untouched.")


@app.command("unarchive")
def unarchive(
    ctx: typer.Context,
    project_id: str = typer.Argument(..., help="Project id."),
) -> None:
    """Bring an archived project back."""
    # FR-13.
    storage = get_context(ctx).require_folder()
    project = unarchive_project(storage, project_id)
    echo(f"Unarchived {accent(project.id)}.")


@app.command("rm")
def remove(
    ctx: typer.Context,
    project_id: str = typer.Argument(..., help="Project id."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask."),
) -> None:
    """Delete a project that has no entries."""
    # FR-16.
    storage = get_context(ctx).require_folder()
    if not yes:
        typer.confirm(f"Delete project {project_id}?", default=False, abort=True)
    project = remove_project(storage, project_id)
    echo(f"Deleted {project.id}.")


@category_app.command("add")
def category_add(
    ctx: typer.Context,
    project_id: str = typer.Argument(..., help="Project id."),
    name: str = typer.Argument(..., help="Category name, without the #."),
) -> None:
    """Register a category on a project up front."""
    # FR-44.
    storage = get_context(ctx).require_folder()
    slug = normalize_category(name)
    project = register_project_category(storage, project_id, slug)
    echo(f"{accent(project.id)} now has {display_category(slug)}.")


@category_app.command("list")
def category_list(
    ctx: typer.Context,
    project_id: str = typer.Argument(..., help="Project id."),
) -> None:
    """List a project's categories, most recently used first."""
    # FR-46.
    storage = get_context(ctx).require_folder()
    project = storage.get_project(project_id)
    ranked = suggest_categories(project, storage.load_all_entries())
    if not ranked:
        echo(f"No categories registered on {project.id} yet.")
        raise typer.Exit()
    for name in ranked:
        echo(display_category(name))


@category_app.command("rm")
def category_remove(
    ctx: typer.Context,
    project_id: str = typer.Argument(..., help="Project id."),
    name: str = typer.Argument(..., help="Category name, without the #."),
) -> None:
    """Unregister a category. Entries that use it keep it."""
    # FR-55.
    storage = get_context(ctx).require_folder()
    project = unregister_project_category(storage, project_id, name)
    echo(f"{accent(project.id)} no longer suggests {display_category(normalize_category(name))}.")
