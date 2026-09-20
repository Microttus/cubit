"""AGENT.md rule 2: core must not import Typer or Flask."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[1] / "src" / "cubit" / "core"
FORBIDDEN = {"typer", "click", "flask", "jinja2", "werkzeug"}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.parametrize("path", sorted(CORE.glob("*.py")), ids=lambda path: path.name)
def test_core_does_not_import_the_interfaces(path: Path) -> None:
    assert not _imported_modules(path) & FORBIDDEN


def test_only_storage_opens_data_files() -> None:
    """AGENT.md rule 3: all reads and writes go through core.storage."""
    offenders = []
    for path in CORE.glob("*.py"):
        if path.name == "storage.py":
            continue
        source = path.read_text(encoding="utf-8")
        if "open(" in source or "write_text(" in source or "read_text(" in source:
            offenders.append(path.name)
    assert offenders == []
