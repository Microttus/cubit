"""The ``cubit menubar`` commands (FR-63, FR-74, FR-75).

rumps is imported only when the app actually starts, so every other command,
and every non-macOS machine, is unaffected by whether it is installed.
"""

from __future__ import annotations

import sys

import typer

from cubit.cli.context import get_context
from cubit.cli.output import accent, echo, muted
from cubit.core import CubitError

app = typer.Typer(
    help="The macOS menu bar app.",
    invoke_without_command=True,
    no_args_is_help=False,
)

#: The install cubit suggests when rumps is missing (FR-75).
INSTALL_HINT = 'Install it with: pipx install "cubit[menubar]"'


def require_macos() -> None:
    """Refuse politely anywhere else (FR-63)."""
    if sys.platform != "darwin":
        raise CubitError(
            "The menu bar app is macOS only.",
            hint="Use 'cubit web' for a local app on this platform.",
        )


def require_rumps() -> None:
    """Check the optional extra is installed, without importing it twice."""
    import importlib.util

    if importlib.util.find_spec("rumps") is None:
        raise CubitError(
            "The menu bar app needs rumps, which is not installed.",
            hint=INSTALL_HINT,
        )


@app.callback()
def menubar(
    ctx: typer.Context,
    port: int = typer.Option(8000, "--port", help="Port the web app uses."),
) -> None:
    """Run the macOS menu bar app."""
    # FR-63. Running it is the default; the subcommands manage the login item.
    if ctx.invoked_subcommand is not None:
        return

    require_macos()
    require_rumps()
    storage = get_context(ctx).require_folder()

    from cubit.menubar.app import run

    echo(f"cubit is in the menu bar. {muted('Quit it from the menu.')}")
    run(storage.data_dir, port)


@app.command("install-login")
def install_login(ctx: typer.Context) -> None:
    """Start the menu bar app when you log in."""
    # FR-74.
    require_macos()
    from cubit.menubar.login import cubit_executable, install, load_command

    program = cubit_executable()
    path = install(program=program)

    echo(f"Wrote {accent(str(path))}")
    echo(muted(f"  it starts {program} menubar at login"))
    echo()
    echo("Load it now with:")
    echo(f"  {accent(load_command(path))}")


@app.command("uninstall-login")
def uninstall_login(ctx: typer.Context) -> None:
    """Stop starting the menu bar app at login."""
    # FR-74.
    require_macos()
    from cubit.menubar.login import plist_path, uninstall, unload_command

    path = plist_path()
    echo("Unload it first, if you have loaded it:")
    echo(f"  {accent(unload_command(path))}")
    echo()

    removed = uninstall()
    if removed is None:
        echo("There was no login item to remove.")
        return
    echo(f"Removed {accent(str(removed))}")
