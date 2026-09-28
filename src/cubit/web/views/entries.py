"""The entries page: list with filters, add, edit, delete and billing (FR-32, FR-81)."""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from cubit.core import (
    UNSET,
    CubitError,
    add_manual_entry,
    edit_entry,
    find_entries,
    format_duration,
    month_bounds,
    remove_entry,
    set_billed,
    total_amount,
)
from cubit.web import forms
from cubit.web.views._shared import category_suggestions, pickable_projects, storage, today

bp = Blueprint("entries", __name__, url_prefix="/entries")


def _filters() -> dict[str, object]:
    """The filters from the query string, defaulting to this month (FR-6)."""
    start = forms.day(request.args, "from")
    end = forms.day(request.args, "to")
    if start is None and end is None and not forms.flag(request.args, "all"):
        start, end = month_bounds(today())

    return {
        "start": start,
        "end": end,
        "project_id": forms.optional(request.args, "project"),
        "client": forms.optional(request.args, "client"),
        "category": forms.optional(request.args, "category"),
        "billed": forms.billing(request.args),
    }


@bp.get("/")
def index():
    store = storage()
    selected = _filters()
    found = find_entries(store, **selected)
    projects = store.load_projects()
    unbilled = [entry for entry in found if not entry.is_billed]

    return render_template(
        "entries.html",
        title="Entries",
        entries=list(reversed(found)),
        total=total_amount(found, store.load_projects_map()),
        unbilled=unbilled,
        unbilled_total=total_amount(unbilled, store.load_projects_map()),
        billed=[entry for entry in found if entry.is_billed],
        billing=forms.text(request.args, "billing", "all"),
        today=today(),
        projects_by_id=store.load_projects_map(),
        projects=projects,
        clients=sorted({project.client for project in projects if project.client}),
        categories=sorted({entry.category for entry in found if entry.category}),
        filters=selected,
        show_all=forms.flag(request.args, "all"),
    )


@bp.get("/new")
def new():
    store = storage()
    projects = pickable_projects(store)
    return render_template(
        "entry_form.html",
        title="Add an entry",
        entry=None,
        projects=projects,
        suggestions=category_suggestions(store, projects),
        default_date=today(),
    )


@bp.post("/")
def create():
    """FR-5."""
    store = storage()
    entry = add_manual_entry(
        store,
        forms.required(request.form, "project_id", "A project"),
        forms.minutes(request.form, "duration"),
        day=forms.day(request.form, "date", default=today()),
        category=forms.optional(request.form, "category"),
        note=forms.text(request.form, "note"),
        start=forms.clock(request.form, "start"),
        force=forms.flag(request.form, "force"),
    )
    flash(f"Logged {entry.duration_minutes} minutes to {entry.project_id}.", "success")
    return redirect(url_for("entries.index"))


@bp.get("/<entry_id>/edit")
def edit(entry_id: str):
    store = storage()
    entry = store.find_entry(entry_id)
    if entry is None:
        abort(404)

    projects = pickable_projects(store, include=entry.project_id)
    return render_template(
        "entry_form.html",
        title=f"Edit {entry.id}",
        entry=entry,
        projects=projects,
        suggestions=category_suggestions(store, projects),
        default_date=entry.date,
    )


@bp.post("/<entry_id>")
def update(entry_id: str):
    """FR-7."""
    store = storage()
    if store.find_entry(entry_id) is None:
        abort(404)

    start = forms.clock(request.form, "start")
    entry = edit_entry(
        store,
        entry_id,
        day=forms.day(request.form, "date") or UNSET,
        duration_minutes=forms.minutes(request.form, "duration"),
        project_id=forms.required(request.form, "project_id", "A project"),
        category=forms.optional(request.form, "category"),
        note=forms.text(request.form, "note"),
        start=start,
        billed_on=forms.day(request.form, "billed_on"),
        force=forms.flag(request.form, "force"),
    )
    flash(f"Updated {entry.id}.", "success")
    return redirect(url_for("entries.index"))


@bp.post("/<entry_id>/delete")
def delete(entry_id: str):
    """FR-7."""
    try:
        entry = remove_entry(storage(), entry_id)
    except CubitError:
        abort(404)
    flash(f"Deleted {entry.id}.", "info")
    return redirect(request.referrer or url_for("entries.index"))


@bp.post("/billed")
def mark_billed():
    """Mark the entries on screen as billed on a day (FR-81).

    The page sends the ids it showed rather than its filters, so an entry
    logged in another window meanwhile is never billed without being seen.
    """
    changed = set_billed(
        storage(),
        forms.many(request.form, "entry_id"),
        forms.day(request.form, "billed_on", default=today()),
    )
    minutes = sum(entry.duration_minutes for entry in changed)
    flash(f"Marked {_count(changed)} ({format_duration(minutes)}) as billed.", "success")
    return redirect(request.referrer or url_for("entries.index"))


@bp.post("/unbilled")
def mark_unbilled():
    """Undo a billing, for entries marked by mistake (FR-81)."""
    changed = set_billed(storage(), forms.many(request.form, "entry_id"), None)
    flash(f"Marked {_count(changed)} as unbilled.", "info")
    return redirect(request.referrer or url_for("entries.index"))


def _count(entries: list) -> str:
    return "1 entry" if len(entries) == 1 else f"{len(entries)} entries"


@bp.app_template_global()
def entries_url(**overrides: object) -> str:
    """The entries page with some filters changed, for the filter chips."""
    args = {key: value for key, value in request.args.items()}
    for key, value in overrides.items():
        if value is None:
            args.pop(key, None)
        else:
            args[key] = value
    return url_for("entries.index", **args)
