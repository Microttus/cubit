"""FR-79: the app bundle's entry point.

``launcher.py`` is what makes one executable do two jobs: the menu bar app when
Finder opens it, the CLI when it is given arguments. The second is not a
nicety -- it is how the menu bar app inside the bundle starts the web app.
"""

from __future__ import annotations

import ast
from pathlib import Path

import launcher

LAUNCHER = Path(launcher.__file__)


def test_finder_arguments_are_not_mistaken_for_commands() -> None:
    """LaunchServices adds -psn_0_12345 when an app is opened from Finder."""
    assert launcher.cli_arguments(["Cubit", "-psn_0_12345"]) == []


def test_the_arguments_after_the_executable_are_the_command() -> None:
    assert launcher.cli_arguments(["Cubit", "web", "--port", "8000"]) == ["web", "--port", "8000"]


def test_a_bare_launch_is_the_menu_bar_app(monkeypatch) -> None:
    started = []
    monkeypatch.setattr(launcher, "run_menu_bar", lambda: started.append("menu bar") or 0)
    monkeypatch.setattr(launcher, "run_cli", lambda _arguments: pytest_fail())

    assert launcher.main(["Cubit"]) == 0
    assert started == ["menu bar"]


def test_arguments_go_to_the_cli(monkeypatch) -> None:
    """The command the bundle runs on itself to start the web app (FR-68)."""
    seen = []
    monkeypatch.setattr(launcher, "run_cli", lambda arguments: seen.append(arguments) or 0)
    monkeypatch.setattr(launcher, "run_menu_bar", lambda: pytest_fail())

    assert launcher.main(["Cubit", "web", "--port", "8000"]) == 0
    assert seen == [["web", "--port", "8000"]]


def pytest_fail() -> None:  # pragma: no cover - only reached by a broken launcher
    raise AssertionError("the wrong half of the launcher ran")


def test_the_launcher_imports_nothing_macos_at_module_level() -> None:
    """AGENT.md: rumps is imported lazily, so the module stays importable."""
    tree = ast.parse(LAUNCHER.read_text(encoding="utf-8"))
    top_level = [node for node in tree.body if isinstance(node, ast.Import | ast.ImportFrom)]
    imported = {
        name.split(".")[0]
        for node in top_level
        for name in (
            [alias.name for alias in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""]
        )
    }
    assert "rumps" not in imported
    assert "cubit" not in imported
