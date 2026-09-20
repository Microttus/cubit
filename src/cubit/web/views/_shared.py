"""Helpers the views share: the storage, and the bits every logging form needs."""

from __future__ import annotations

from datetime import date

from flask import current_app

from cubit.core import Entry, Project, Storage, active_projects, suggest_categories


def storage() -> Storage:
    """The storage this app was built over."""
    return current_app.config["CUBIT_STORAGE"]


def pickable_projects(store: Storage, include: str | None = None) -> list[Project]:
    """Projects a picker should offer: the active ones (FR-13).

    ``include`` keeps one archived project in the list, so editing an old entry
    does not silently move it to another project.
    """
    projects = store.load_projects()
    offered = active_projects(projects)
    if include and not any(project.id == include for project in offered):
        extra = next((project for project in projects if project.id == include), None)
        if extra is not None:
            offered = [*offered, extra]
    return offered


def category_suggestions(
    store: Storage, projects: list[Project], entries: list[Entry] | None = None
) -> dict[str, list[str]]:
    """Ranked categories per project, for the autocomplete (FR-46, FR-50)."""
    history = store.load_all_entries() if entries is None else entries
    return {project.id: suggest_categories(project, history) for project in projects}


def today() -> date:
    return date.today()
