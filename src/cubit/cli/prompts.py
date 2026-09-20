"""Interactive bits of logging: confirming a new category and suggesting one.

The rules live in ``cubit.core``; this module only asks the questions
(FR-45, FR-52, FR-53).
"""

from __future__ import annotations

import sys

import typer

from cubit.cli.output import accent, muted
from cubit.core import CategoryCheck, Project, check_category, display_category

#: How many suggestions a prompt offers before it gets in the way.
SUGGESTION_LIMIT = 5


def interactive() -> bool:
    """True only when there is a real terminal to ask on (FR-53)."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def confirm_category(
    project: Project,
    name: str,
    *,
    assume_yes: bool = False,
) -> str | None:
    """Turn a typed category into the slug to store, asking when it is new.

    Returns ``None`` if the user backs out. A name that is already registered
    passes straight through, so the common case asks nothing (FR-45).
    """
    result = check_category(project, name)
    if result.is_registered or assume_yes or not interactive():
        return result.slug

    if result.did_you_mean:
        # FR-52: catch the typo before it becomes a second category.
        suggestion = display_category(result.did_you_mean)
        if typer.confirm(f"Did you mean {suggestion}?", default=True):
            return result.did_you_mean

    if typer.confirm(
        f"{display_category(result.slug)} is new to {project.id}. Register it?",
        default=True,
    ):
        return result.slug
    return None


def choose_category(
    project: Project,
    suggestions: list[str],
    *,
    enabled: bool = True,
) -> str | None:
    """Offer the project's top categories as a numbered list (FR-53).

    Enter picks nothing. Anything that is not a number is taken as a new
    category name, which then goes through :func:`confirm_category`.
    """
    if not enabled or not suggestions or not interactive():
        return None

    typer.echo(muted(f"Categories for {project.id}:"))
    shown = suggestions[:SUGGESTION_LIMIT]
    for number, slug in enumerate(shown, start=1):
        typer.echo(f"  {accent(str(number))}  {display_category(slug)}")

    answer = typer.prompt(
        "Category (number, name, or Enter to skip)", default="", show_default=False
    )
    answer = answer.strip()
    if not answer:
        return None
    if answer.isdigit() and 1 <= int(answer) <= len(shown):
        return shown[int(answer) - 1]
    return confirm_category(project, answer)


def describe_check(result: CategoryCheck) -> str:
    """A short line about what will happen to a category, for non-interactive runs."""
    if result.is_registered:
        return f"{display_category(result.slug)}"
    return f"{display_category(result.slug)} (new)"
