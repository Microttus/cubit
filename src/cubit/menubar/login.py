"""Starting the menu bar app at login, with a LaunchAgent (FR-74).

Writing the plist is a pure function of the path to ``cubit``, so it can be
tested without macOS and without touching the real LaunchAgents folder.
Loading the agent is left to the user: ``launchctl`` changes the state of their
session, which is not something a test, or an install command, should do behind
their back.
"""

from __future__ import annotations

import plistlib
import shutil
import sys
from pathlib import Path

from cubit.core import CubitError

#: The reverse-DNS label macOS knows the agent by (FR-74).
LABEL = "no.icecubesol.cubit"

#: Where a per-user LaunchAgent lives.
AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"


def plist_path(agents_dir: Path | None = None) -> Path:
    return (agents_dir or AGENTS_DIR) / f"{LABEL}.plist"


def cubit_executable() -> str:
    """The absolute path to the installed ``cubit``.

    An absolute path matters: launchd starts an agent with a bare environment,
    so a pipx or virtualenv install is not on its PATH and a bare ``cubit``
    would simply never start.
    """
    found = shutil.which("cubit")
    if found:
        return str(Path(found).resolve())

    beside = Path(sys.executable).parent / "cubit"
    if beside.exists():
        return str(beside.resolve())

    raise CubitError(
        "Cannot find the cubit executable.",
        hint="Install cubit with 'pipx install \".[menubar]\"' and try again.",
    )


def launch_agent_plist(program: str, label: str = LABEL) -> bytes:
    """The LaunchAgent that starts the menu bar app at login (FR-74).

    ``RunAtLoad`` starts it when the user logs in. ``KeepAlive`` is false on
    purpose: quitting from the menu means quitting, and launchd must not bring
    the app straight back (FR-69).
    """
    if not program:
        raise CubitError("A LaunchAgent needs the path to cubit.")

    return plistlib.dumps(
        {
            "Label": label,
            "ProgramArguments": [program, "menubar"],
            "RunAtLoad": True,
            "KeepAlive": False,
            "ProcessType": "Interactive",
        }
    )


def load_command(path: Path) -> str:
    """The command that tells launchd about the agent, for us to print."""
    return f"launchctl load -w {path}"


def unload_command(path: Path) -> str:
    return f"launchctl unload -w {path}"


def install(agents_dir: Path | None = None, program: str | None = None) -> Path:
    """Write the LaunchAgent and return where it went."""
    target = plist_path(agents_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(launch_agent_plist(program or cubit_executable()))
    return target


def uninstall(agents_dir: Path | None = None) -> Path | None:
    """Remove the LaunchAgent. ``None`` when there was nothing to remove."""
    target = plist_path(agents_dir)
    if not target.exists():
        return None
    target.unlink()
    return target
