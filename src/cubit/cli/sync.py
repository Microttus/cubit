"""The ``cubit sync`` commands: keep the data folder in step between computers (FR-82)."""

from __future__ import annotations

import typer

from cubit.cli.context import get_context
from cubit.cli.output import accent, echo, muted
from cubit.core import check_data, run_sync, setup_sync

app = typer.Typer(
    help="Sync the data folder between computers through a git remote.",
    invoke_without_command=True,
    no_args_is_help=False,
)


@app.callback()
def sync_command(
    ctx: typer.Context,
    message: str | None = typer.Option(None, "--message", "-m", help="Commit message."),
) -> None:
    """Commit local changes, pull the other computer's, and push."""
    if ctx.invoked_subcommand is not None:
        return

    storage = get_context(ctx).require_folder()
    report = run_sync(storage, message)

    if report.committed:
        echo("Saved your changes.")
    if report.pulled:
        echo(f"Brought in {report.pulled} {'change' if report.pulled == 1 else 'changes'}.")
    if report.pushed:
        echo("Uploaded.")
    if not (report.committed or report.pulled or report.pushed):
        echo("Already in sync.")

    if report.pulled:
        problems = check_data(storage)
        if problems.has_errors:
            echo(muted("The merged data has errors. Run 'cubit check' to see them."))


@app.command("setup")
def setup(
    ctx: typer.Context,
    remote: str | None = typer.Argument(
        None,
        help="The git URL to sync to. On a computer with no data folder, it is cloned.",
    ),
) -> None:
    """Start syncing this data folder (or fetch it on a new computer)."""
    storage = get_context(ctx).storage
    report = setup_sync(storage, remote)

    if report.cloned:
        echo(f"Cloned the data into {accent(str(storage.data_dir))}")
    elif report.initialised:
        echo(f"Made {accent(str(storage.data_dir))} a git repository.")
    echo(muted("  .state/ stays on this computer: the running timer is not synced"))
    if report.pushed:
        echo("Uploaded. From now on, 'cubit sync' keeps the computers in step.")
    else:
        echo("No remote yet. Run this again with the git URL to finish.")
