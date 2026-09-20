"""FR-63 and FR-74 from the command line, on whatever platform this is."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from cubit.cli import menubar
from cubit.cli.exit_codes import EXIT_ERROR, EXIT_OK
from cubit.core import CubitError


@pytest.fixture
def elsewhere(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend we are not on macOS."""
    monkeypatch.setattr(menubar.sys, "platform", "linux")


@pytest.fixture
def on_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(menubar.sys, "platform", "darwin")


def test_the_command_is_registered(cli) -> None:
    assert "menubar" in cli("--help").stdout


def test_menubar_help_lists_the_login_commands(cli) -> None:
    """FR-24, FR-74."""
    result = cli("menubar", "--help")
    assert result.exit_code == EXIT_OK
    assert "install-login" in result.stdout
    assert "uninstall-login" in result.stdout
    assert "FR-" not in result.stdout


def test_on_another_platform_it_says_so(cli, elsewhere: None) -> None:
    """FR-63: the command exists everywhere and refuses politely."""
    result = cli("menubar")

    assert result.exit_code == EXIT_ERROR
    assert "macOS only" in result.output
    assert "cubit web" in result.output
    assert "Traceback" not in result.output


def test_install_login_on_another_platform(cli, elsewhere: None) -> None:
    result = cli("menubar", "install-login")
    assert result.exit_code == EXIT_ERROR
    assert "macOS only" in result.output


def test_uninstall_login_on_another_platform(cli, elsewhere: None) -> None:
    result = cli("menubar", "uninstall-login")
    assert result.exit_code == EXIT_ERROR
    assert "macOS only" in result.output


def test_require_macos_passes_on_darwin(on_macos: None) -> None:
    menubar.require_macos()  # does not raise


def test_a_missing_rumps_says_how_to_install_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-75: the extra is optional, so the message has to name it."""
    import importlib.util

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)

    with pytest.raises(CubitError) as caught:
        menubar.require_rumps()

    assert "rumps" in caught.value.message
    assert "pipx install" in (caught.value.hint or "")
    assert "menubar" in (caught.value.hint or "")


def test_rumps_present_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.util

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    menubar.require_rumps()  # does not raise


@pytest.mark.skipif(sys.platform == "darwin", reason="rumps may really be installed")
def test_the_menubar_command_does_not_need_rumps_to_exist(cli) -> None:
    """Every other command must work on a machine without the extra."""
    assert cli("--help").exit_code == EXIT_OK
    assert cli("status").exit_code == EXIT_OK


def test_the_cli_never_imports_rumps_by_itself() -> None:
    """FR-75: importing the CLI must not need the optional extra."""
    import subprocess

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import cubit.cli.main, sys; print('rumps' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "False"


def test_install_login_writes_a_plist_and_prints_the_command(
    cli, on_macos: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """FR-74: we write the file and tell them the launchctl command."""
    agents = tmp_path / "LaunchAgents"
    fake = tmp_path / "cubit"
    fake.write_text("#!/bin/sh\n")

    monkeypatch.setattr("cubit.menubar.login.AGENTS_DIR", agents)
    monkeypatch.setattr("shutil.which", lambda name: str(fake))

    result = cli("menubar", "install-login")

    assert result.exit_code == EXIT_OK
    assert (agents / "no.icecubesol.cubit.plist").exists()
    assert "launchctl load -w" in result.stdout
    assert str(fake) in result.stdout


def test_uninstall_login_removes_it(
    cli, on_macos: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    agents = tmp_path / "LaunchAgents"
    fake = tmp_path / "cubit"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.setattr("cubit.menubar.login.AGENTS_DIR", agents)
    monkeypatch.setattr("shutil.which", lambda name: str(fake))

    cli("menubar", "install-login")
    result = cli("menubar", "uninstall-login")

    assert result.exit_code == EXIT_OK
    assert not (agents / "no.icecubesol.cubit.plist").exists()
    assert "launchctl unload -w" in result.stdout


def test_uninstall_login_when_there_is_nothing_to_remove(
    cli, on_macos: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("cubit.menubar.login.AGENTS_DIR", tmp_path / "LaunchAgents")

    result = cli("menubar", "uninstall-login")

    assert result.exit_code == EXIT_OK
    assert "no login item" in result.stdout


def test_install_login_never_runs_launchctl(
    cli, on_macos: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Loading an agent changes the user's session; that is their call."""
    import subprocess

    fake = tmp_path / "cubit"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.setattr("cubit.menubar.login.AGENTS_DIR", tmp_path / "LaunchAgents")
    monkeypatch.setattr("shutil.which", lambda name: str(fake))

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("the install command ran a subprocess")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)

    assert cli("menubar", "install-login").exit_code == EXIT_OK
