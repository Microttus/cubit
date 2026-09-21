"""Entry point for the macOS app bundle (FR-79).

PyInstaller freezes this module rather than ``cubit.cli.main``, because the
bundle has two jobs. Double-clicked in Finder it is the menu bar app; run with
arguments it is the ordinary CLI. That second job is not a convenience: the web
app the menu bar opens is started as this same executable with ``web`` after
it, which is the only thing a frozen app can start. There is no ``cubit`` on
the PATH a GUI app inherits, and ``sys.executable -m cubit.cli.main`` does not
work inside a bundle, where ``sys.executable`` is the bundle itself.

Nothing here imports rumps at module level, so the module stays importable, and
testable, on any machine.
"""

from __future__ import annotations

import sys

#: LaunchServices adds this when an app is opened from Finder. It is not ours,
#: and it must not be mistaken for a command.
PROCESS_SERIAL_PREFIX = "-psn_"


def cli_arguments(argv: list[str]) -> list[str]:
    """The arguments meant for the CLI, or an empty list for the menu bar."""
    return [argument for argument in argv[1:] if not argument.startswith(PROCESS_SERIAL_PREFIX)]


def run_cli(arguments: list[str]) -> int:
    """Hand over to the normal cubit CLI, errors, exit codes and all."""
    from cubit.cli.main import app

    app(args=arguments, prog_name="cubit")
    return 0  # pragma: no cover - click exits the process itself


def run_menu_bar() -> int:
    """Start the menu bar app, reporting a missing folder in a window.

    A bundled app has no terminal to print to, so the one error a first run can
    realistically hit -- no data folder yet -- is a dialog that offers to make
    one, rather than an app that appears not to start at all.
    """
    import rumps

    from cubit.cli.context import build_context
    from cubit.core import CubitError
    from cubit.menubar.app import run
    from cubit.web import DEFAULT_PORT

    context = build_context(None)
    try:
        storage = context.require_folder()
    except CubitError as error:
        clicked = rumps.alert(
            title="Cubit has no data folder yet",
            message=f"{error.message}\n\nCreate one now?",
            ok="Create folder",
            cancel="Quit",
        )
        if not clicked:
            return 1
        context.storage.init()
        storage = context.storage

    run(storage.data_dir, DEFAULT_PORT)
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = cli_arguments(sys.argv if argv is None else argv)
    return run_cli(arguments) if arguments else run_menu_bar()


if __name__ == "__main__":
    raise SystemExit(main())
