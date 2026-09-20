"""AGENT.md rule 2: core must not import Typer or Flask."""

from __future__ import annotations

import ast
import re
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


WEB = Path(__file__).resolve().parents[1] / "src" / "cubit" / "web"
STATIC = WEB / "static"
TEMPLATES = WEB / "templates"

#: Anything that looks like a colour written out by hand.
COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")


def test_the_web_app_does_not_open_data_files() -> None:
    """AGENT.md rule 3: all reads and writes go through core.storage."""
    offenders = []
    for path in WEB.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "open(" in source or "write_text(" in source or "read_text(" in source:
            offenders.append(path.name)
    assert offenders == []


def test_only_theme_css_defines_colours() -> None:
    """FR-57: changing the theme means editing one file."""
    offenders = []
    for path in [*STATIC.glob("*.css"), *TEMPLATES.rglob("*.html")]:
        if path.name == "theme.css":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if COLOUR.search(line):
                offenders.append(f"{path.name}:{number}")
    assert offenders == []


def test_the_stylesheet_uses_the_theme_tokens() -> None:
    """The components are built from the variables, not around them."""
    app_css = (STATIC / "app.css").read_text(encoding="utf-8")
    # The page background belongs to theme.css; the components use the rest.
    for token in [
        "--color-surface",
        "--color-accent",
        "--color-border",
        "--font-mono",
        "--radius-card",
        "--space-4",
    ]:
        assert token in app_css


def test_every_theme_token_the_requirements_list_exists() -> None:
    """REQUIREMENTS 4.5 names these; the app is built on them."""
    theme = (STATIC / "theme.css").read_text(encoding="utf-8")
    for token in [
        "--color-bg",
        "--color-surface",
        "--color-surface-raised",
        "--color-border",
        "--color-text",
        "--color-text-muted",
        "--color-accent",
        "--color-accent-hover",
        "--color-accent-contrast",
        "--color-success",
        "--color-warning",
        "--color-danger",
        "--font-body",
        "--font-mono",
        "--radius-card",
        "--radius-pill",
        "--header-h",
    ]:
        assert f"{token}:" in theme, token


def test_the_theme_has_both_a_dark_and_a_light_value() -> None:
    """FR-62: dark by default, light "ice" available."""
    theme = (STATIC / "theme.css").read_text(encoding="utf-8")
    assert "color-scheme: dark" in theme
    assert 'data-theme="light"' in theme
    assert theme.count("light-dark(") >= 15


def test_the_bundled_font_is_the_open_source_one() -> None:
    """Only JetBrains Mono ships with the app; Sans is not redistributable."""
    theme = (STATIC / "theme.css").read_text(encoding="utf-8")
    assert "JetBrainsMono" in theme
    assert "JetBrainsSans" not in theme
    assert (STATIC / "fonts" / "README.md").exists()


def test_the_font_is_actually_bundled() -> None:
    """FR-58: the app must not need the network to look right."""
    font = STATIC / "fonts" / "JetBrainsMono-Regular.woff2"
    assert font.exists(), "the bundled font is missing"
    assert font.read_bytes()[:4] == b"wOF2", "that is not a woff2 file"
    assert (STATIC / "fonts" / "OFL.txt").exists(), "a bundled font ships its licence"


def test_every_font_the_theme_asks_for_is_present() -> None:
    """A @font-face pointing at a missing file is a 404 on every page load."""
    theme = (STATIC / "theme.css").read_text(encoding="utf-8")
    for name in re.findall(r'url\("fonts/([^"]+)"\)', theme):
        assert (STATIC / "fonts" / name).exists(), name
