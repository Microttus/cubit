"""The ``cubit check`` command: validate the whole data folder."""

from __future__ import annotations

from pathlib import Path

import typer

from cubit.cli.context import get_context
from cubit.cli.exit_codes import EXIT_ERROR
from cubit.cli.output import DANGER, WARNING, echo, muted, paint
from cubit.core import ERROR, Problem, check_data


def check(
    ctx: typer.Context,
    strict: bool = typer.Option(False, "--strict", help="Treat warnings as failures too."),
) -> None:
    """Validate the data folder and report anything wrong with it."""
    # FR-41.
    storage = get_context(ctx).require_folder()
    report = check_data(storage)

    for problem in report.problems:
        colour = DANGER if problem.level == ERROR else WARNING
        echo(f"{paint(problem.level, colour)}  {_describe(problem, storage.data_dir)}")

    if report.problems:
        echo()

    echo(
        muted(
            f"Checked {report.projects} projects and {report.entries} entries "
            f"across {report.months} monthly files."
        )
    )

    if report.is_clean:
        echo("Everything checks out.")
        return

    echo(
        f"{len(report.errors)} {'error' if len(report.errors) == 1 else 'errors'}, "
        f"{len(report.warnings)} {'warning' if len(report.warnings) == 1 else 'warnings'}."
    )
    if report.has_errors or (strict and report.warnings):
        raise typer.Exit(code=EXIT_ERROR)


def _describe(problem: Problem, data_dir: Path) -> str:
    """A problem with its path written relative to the data folder."""
    if problem.path is None:
        return problem.message
    try:
        where = str(problem.path.relative_to(data_dir))
    except ValueError:
        where = str(problem.path)
    if problem.row is not None:
        where = f"{where} row {problem.row}"
    return f"{where}: {problem.message}"
