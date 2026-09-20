"""Entry point for the ``cubit`` command.

Milestone 1 only wires up the executable so the console script works.
The real commands arrive in milestone 2.
"""

from __future__ import annotations

import typer

from cubit import __version__

app = typer.Typer(
    name="cubit",
    help="Time logging for a one-person company.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"cubit {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show the version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Cubit command-line interface."""
