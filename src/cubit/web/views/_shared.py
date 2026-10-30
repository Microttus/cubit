"""Helpers the views share: the storage, and the bits every logging form needs."""

from __future__ import annotations

from datetime import date

from flask import current_app, flash

from cubit.core import (
    CubitError,
    Entry,
    Project,
    Storage,
    SyncReport,
    active_projects,
    is_configured,
    run_sync,
    suggest_categories,
)


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


def describe_sync(report: SyncReport) -> str:
    """What a sync did, in a sentence for the flash message."""
    parts = []
    if report.committed:
        parts.append("saved your changes")
    if report.pulled:
        parts.append(f"brought in {report.pulled} {'change' if report.pulled == 1 else 'changes'}")
    if report.pushed:
        parts.append("uploaded")
    if not parts:
        return "Already in sync."
    return f"Synced: {', '.join(parts)}."


def _try_sync(store: Storage, failure: str) -> SyncReport | None:
    """Run a sync that must never stop the request it belongs to.

    A folder that does not sync, or a running timer (which does not sync), is
    not worth a message each time, so those return None quietly. A sync that
    fails becomes a warning that starts with ``failure``.
    """
    if not is_configured(store) or store.read_timer() is not None:
        return None
    try:
        return run_sync(store)
    except CubitError as error:
        detail = error.message if not error.hint else f"{error.message} {error.hint}"
        flash(f"{failure} {detail}", "warning")
        return None


def sync_before_change(store: Storage) -> None:
    """Bring in the other computer's changes before logging or starting (FR-82).

    Only a failure is reported: the work goes ahead on what is here, and the
    sync after it tries again.
    """
    _try_sync(store, "Could not sync first, so this is on top of what is here.")


def sync_after_change(store: Storage) -> None:
    """Upload what was just logged (FR-82). The entry is already saved."""
    report = _try_sync(store, "Saved, but the sync failed.")
    if report is not None and (report.pulled or report.pushed):
        flash(describe_sync(report), "info")
