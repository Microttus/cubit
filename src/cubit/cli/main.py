"""Entry point for the ``cubit`` command.

The CLI is a thin layer: it parses options, calls :mod:`cubit.core` and prints
what comes back. Any :class:`~cubit.core.CubitError` raised underneath is turned
into a short message, its hint and a non-zero exit code, never a traceback
(FR-25).
"""

from __future__ import annotations

from typing import Any

import click
import typer
from typer.core import TyperGroup

from cubit import __version__
from cubit.cli import check as check_module
from cubit.cli import entries, projects, reports
from cubit.cli.completion import complete_shell, completion_script
from cubit.cli.context import build_context, get_context
from cubit.cli.exit_codes import EXIT_ERROR
from cubit.cli.output import accent, echo, muted, paint
from cubit.core import CubitError


class ErrorHandlingGroup(TyperGroup):
    """Turns a CubitError from any command into a clean message (FR-25)."""

    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except CubitError as error:
            _report(error)
            raise typer.Exit(code=EXIT_ERROR) from None


def _report(error: CubitError) -> None:
    typer.echo(paint(f"Error: {error.message}", typer.colors.RED), err=True)
    if error.hint:
        typer.echo(muted(f"Hint: {error.hint}"), err=True)


app = typer.Typer(
    cls=ErrorHandlingGroup,
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
    ctx: typer.Context,
    data_dir: str | None = typer.Option(
        None,
        "--data-dir",
        envvar="CUBIT_DATA_DIR",
        help="Data folder to work on. Defaults to ~/cubit-data.",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        help="Show the version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Cubit command-line interface."""
    ctx.obj = build_context(data_dir)


@app.command()
def init(ctx: typer.Context) -> None:
    """Create the data folder and its starter files."""
    app_ctx = get_context(ctx)
    created = app_ctx.storage.init()

    if created:
        echo(f"Created a cubit data folder at {accent(str(app_ctx.data_dir))}")
    else:
        echo(f"Data folder already set up at {accent(str(app_ctx.data_dir))}")
    echo(muted("  config.yaml, projects.yaml and entries/ are ready."))
    echo()
    echo('Next: cubit project add acme-web --name "Acme website" --client "Acme Corp" --rate 95')


@app.command()
def completion(
    shell: str = typer.Argument(
        ...,
        help="Which shell to write a script for: bash, zsh or fish.",
        autocompletion=complete_shell,
    ),
) -> None:
    """Print a shell tab-completion script for cubit."""
    # FR-29. Pipe it into your shell config, for example:
    #   cubit completion zsh >> ~/.zshrc
    typer.echo(completion_script(shell.lower()))


@app.command()
def web(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", "--host", help="Interface to listen on."),
    port: int = typer.Option(8000, "--port", help="Port to listen on."),
) -> None:
    """Start the local web app."""
    # FR-30, FR-35: loopback only, and nothing is fetched from the internet.
    # Imported here so the rest of the CLI never has to load Flask.
    from cubit.web import create_app

    app_ctx = get_context(ctx)
    app_ctx.require_folder()
    flask_app = create_app(app_ctx.data_dir)

    echo(f"cubit is at {accent(f'http://{host}:{port}')}")
    echo(muted(f"  data folder {app_ctx.data_dir}"))
    echo(muted("  press ctrl-c to stop"))
    flask_app.run(host=host, port=port, debug=False)


entries.register(app)
app.command("check")(check_module.check)
app.add_typer(projects.app, name="project")
app.add_typer(reports.app, name="report")


if __name__ == "__main__":  # pragma: no cover - exercised as a subprocess
    app()
