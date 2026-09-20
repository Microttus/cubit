"""Tab-completion for project ids and categories (FR-29).

Typer gives ``--install-completion`` for the commands themselves; these
callbacks add the values. A completion callback runs on every press of the tab
key, in the middle of someone's typing, so it must be quick and must never
raise: an exception here would print a traceback into the user's prompt.
"""

from __future__ import annotations

from cubit.core import Storage, resolve_data_dir


def _storage() -> Storage | None:
    """The data folder from the environment or the default.

    A completion callback does not get the parsed ``--data-dir``, so this only
    sees ``CUBIT_DATA_DIR`` and the default. That covers the normal case.
    """
    try:
        storage = Storage(resolve_data_dir())
    except Exception:  # noqa: BLE001 - completion never fails loudly
        return None
    return storage if storage.exists else None


def complete_project(incomplete: str) -> list[str]:
    """Active project ids, with the name as the description."""
    storage = _storage()
    if storage is None:
        return []
    try:
        projects = storage.load_projects()
    except Exception:  # noqa: BLE001 - a broken file must not break the prompt
        return []
    return [
        project.id
        for project in projects
        if project.is_active and project.id.startswith(incomplete)
    ]


def complete_any_project(incomplete: str) -> list[str]:
    """Every project id, archived ones included, for commands that manage them."""
    storage = _storage()
    if storage is None:
        return []
    try:
        projects = storage.load_projects()
    except Exception:  # noqa: BLE001
        return []
    return [project.id for project in projects if project.id.startswith(incomplete)]


def complete_category(incomplete: str) -> list[str]:
    """Every category registered on any project.

    The shell cannot tell us which project the user already typed, so this
    offers all of them; the prompts narrow to one project (FR-46, FR-53).
    """
    storage = _storage()
    if storage is None:
        return []
    try:
        projects = storage.load_projects()
    except Exception:  # noqa: BLE001
        return []
    names = {name for project in projects for name in project.categories}
    return sorted(name for name in names if name.startswith(incomplete))


def complete_client(incomplete: str) -> list[str]:
    """Client names, for the per-client report."""
    storage = _storage()
    if storage is None:
        return []
    try:
        projects = storage.load_projects()
    except Exception:  # noqa: BLE001
        return []
    names = {project.client for project in projects if project.client}
    return sorted(name for name in names if name.lower().startswith(incomplete.lower()))


def complete_format(incomplete: str) -> list[str]:
    """The values --format accepts (FR-23)."""
    from cubit.core import FORMATS

    return [name for name in FORMATS if name.startswith(incomplete)]


#: The shells a completion script can be written for. PowerShell is in the list
#: because cubit supports Windows (REQUIREMENTS section 5).
SHELLS = ("bash", "zsh", "fish", "powershell", "pwsh")

#: The variable the generated script calls cubit back through.
COMPLETE_VAR = "_CUBIT_COMPLETE"


def completion_script(shell: str) -> str:
    """The completion script for ``shell`` (FR-29).

    Typer's own ``--install-completion`` has to guess which shell you are in,
    and gives up whenever cubit was not started from an interactive prompt.
    This takes the shell as an argument instead, so it always works.

    The script has to speak the protocol Typer's completion handler expects,
    which is not the one click writes by default, so it comes from Typer's own
    generator rather than from click's completion classes. That is a private
    module, so a test round-trips a real completion through the script to catch
    it changing.
    """
    from typer._completion_shared import get_completion_script

    from cubit.core import CubitError

    if shell not in SHELLS:
        raise CubitError(
            f"Cannot write a completion script for {shell!r}.",
            hint=f"Choose one of {', '.join(SHELLS)}.",
        )
    return get_completion_script(prog_name="cubit", complete_var=COMPLETE_VAR, shell=shell)


def complete_shell(incomplete: str) -> list[str]:
    return [name for name in SHELLS if name.startswith(incomplete)]
