"""FR-74: the LaunchAgent that starts the menu bar app at login.

Generating the plist is pure, so these run anywhere. Nothing here calls
launchctl or touches the real ~/Library/LaunchAgents.
"""

from __future__ import annotations

import plistlib
from pathlib import Path

import pytest

from cubit.core import CubitError
from cubit.menubar.login import (
    LABEL,
    cubit_executable,
    install,
    launch_agent_plist,
    load_command,
    plist_path,
    uninstall,
    unload_command,
)

PROGRAM = "/Users/someone/.local/bin/cubit"


def parsed(program: str = PROGRAM) -> dict:
    return plistlib.loads(launch_agent_plist(program))


def test_the_label_is_the_documented_one() -> None:
    assert LABEL == "no.icecubesol.cubit"
    assert parsed()["Label"] == LABEL


def test_the_agent_runs_cubit_menubar() -> None:
    assert parsed()["ProgramArguments"] == [PROGRAM, "menubar"]


def test_the_agent_starts_at_login_and_does_not_come_back() -> None:
    """RunAtLoad true, KeepAlive false: quitting means quitting (FR-69)."""
    plist = parsed()
    assert plist["RunAtLoad"] is True
    assert plist["KeepAlive"] is False


def test_the_program_path_is_absolute() -> None:
    """launchd has no PATH, so a bare 'cubit' would simply never start."""
    assert Path(parsed()["ProgramArguments"][0]).is_absolute()


def test_the_plist_is_valid_xml() -> None:
    raw = launch_agent_plist(PROGRAM)
    assert raw.startswith(b"<?xml")
    assert plistlib.loads(raw)  # round-trips


def test_an_empty_program_is_refused() -> None:
    with pytest.raises(CubitError, match="path to cubit"):
        launch_agent_plist("")


def test_the_label_can_be_overridden_for_testing() -> None:
    assert plistlib.loads(launch_agent_plist(PROGRAM, "test.label"))["Label"] == "test.label"


def test_where_the_plist_goes() -> None:
    assert plist_path().parent.name == "LaunchAgents"
    assert plist_path().name == f"{LABEL}.plist"


def test_install_writes_the_file(tmp_path: Path) -> None:
    agents = tmp_path / "LaunchAgents"

    written = install(agents_dir=agents, program=PROGRAM)

    assert written == agents / f"{LABEL}.plist"
    assert plistlib.loads(written.read_bytes())["ProgramArguments"][0] == PROGRAM


def test_install_creates_the_folder_if_it_is_missing(tmp_path: Path) -> None:
    agents = tmp_path / "nested" / "LaunchAgents"
    assert install(agents_dir=agents, program=PROGRAM).exists()


def test_installing_twice_replaces_the_file(tmp_path: Path) -> None:
    agents = tmp_path / "LaunchAgents"
    install(agents_dir=agents, program="/old/cubit")
    written = install(agents_dir=agents, program=PROGRAM)

    assert plistlib.loads(written.read_bytes())["ProgramArguments"][0] == PROGRAM


def test_uninstall_removes_the_file(tmp_path: Path) -> None:
    agents = tmp_path / "LaunchAgents"
    install(agents_dir=agents, program=PROGRAM)

    removed = uninstall(agents_dir=agents)

    assert removed is not None
    assert not removed.exists()


def test_uninstalling_what_is_not_there_is_not_an_error(tmp_path: Path) -> None:
    assert uninstall(agents_dir=tmp_path / "LaunchAgents") is None


def test_the_commands_we_print_are_the_launchctl_ones(tmp_path: Path) -> None:
    """We tell the user the command; we do not change their session for them."""
    path = tmp_path / "x.plist"
    assert load_command(path) == f"launchctl load -w {path}"
    assert unload_command(path) == f"launchctl unload -w {path}"


def test_the_executable_is_found_on_the_path(monkeypatch, tmp_path: Path) -> None:
    fake = tmp_path / "cubit"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.setattr("shutil.which", lambda name: str(fake))

    assert cubit_executable() == str(fake.resolve())


def test_the_executable_is_found_beside_the_interpreter(monkeypatch, tmp_path: Path) -> None:
    """A virtualenv install is not always on the PATH of whatever ran us."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "cubit").write_text("#!/bin/sh\n")
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr("sys.executable", str(bin_dir / "python"))

    assert cubit_executable() == str((bin_dir / "cubit").resolve())


def test_a_missing_executable_says_how_to_install_it(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr("sys.executable", str(tmp_path / "bin" / "python"))

    with pytest.raises(CubitError) as caught:
        cubit_executable()
    assert "pipx install" in (caught.value.hint or "")
