"""The entries page: list with filters, add, edit and delete (FR-32)."""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from cubit.core import (
    UNSET,
    CubitError,
    add_manual_entry,
    edit_entry,
    find_entries,
    month_bounds,
    remove_entry,
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
    }


@bp.get("/")
def index():
    store = storage()
    selected = _filters()
    found = find_entries(store, **selected)
    projects = store.load_projects()

    return render_template(
        "entries.html",
        title="Entries",
        entries=list(reversed(found)),
        total=total_amount(found, store.load_projects_map()),
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
