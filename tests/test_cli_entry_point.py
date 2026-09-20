"""The console script exists and reports its version. Commands arrive in M2."""

from __future__ import annotations

import subprocess
import sys

from cubit import __version__


def test_version_flag() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "cubit.cli.main", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == f"cubit {__version__}"


def test_help_is_available() -> None:
    """FR-24: every command has --help."""
    result = subprocess.run(
        [sys.executable, "-m", "cubit.cli.main", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "cubit" in result.stdout.lower()
