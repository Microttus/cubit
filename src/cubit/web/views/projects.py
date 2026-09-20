"""The projects page: create, edit, rate history, archive (FR-33)."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from cubit.core import (
    archive_project,
    create_project,
    edit_project,
    project_report,
    register_project_category,
    remove_project,
    set_rate,
    suggest_categories,
    unarchive_project,
    unregister_project_category,
)
from cubit.web import forms
from cubit.web.views._shared import storage, today

bp = Blueprint("projects", __name__, url_prefix="/projects")


@bp.get("/")
def index():
    store = storage()
    show_all = forms.flag(request.args, "all")
    projects = store.load_projects()
    entries = store.load_all_entries()

    logged: dict[str, int] = {}
    for entry in entries:
        logged[entry.project_id] = logged.get(entry.project_id, 0) + entry.duration_minutes

    return render_template(
        "projects.html",
        title="Projects",
        projects=[p for p in projects if show_all or p.is_active],
        archived_count=sum(1 for project in projects if not project.is_active),
        logged=logged,
        show_all=show_all,
        today=today(),
    )


@bp.get("/new")
def new():
    return render_template("project_form.html", title="New project", project=None)


@bp.post("/")
def create():
    """FR-11."""
    store = storage()
    project = create_project(
        store,
        forms.required(request.form, "id", "An id"),
        name=forms.required(request.form, "name", "A name"),
        client=forms.text(request.form, "client"),
        budget_hours=forms.hours(request.form, "budget_hours"),
        rate=forms.money(request.form, "rate", "a rate"),
        rate_from=forms.day(request.form, "rate_from"),
    )
    flash(f"Created {project.id}.", "success")
    return redirect(url_for("projects.detail", project_id=project.id))


@bp.get("/<project_id>")
def detail(project_id: str):
    store = storage()
    project = store.get_project(project_id)
    entries = store.load_all_entries()
    config = store.load_config()

    report = project_report(
        project,
        entries,
        store.load_projects_map(),
        warning_percent=config.budget_warning_percent,
    )
    return render_template(
        "project_detail.html",
        title=project.name,
        project=project,
        report=report,
        suggestions=suggest_categories(project, entries),
        today=today(),
    )


@bp.post("/<project_id>")
def update(project_id: str):
    """FR-11, FR-12: everything but the id."""
    project = edit_project(
        storage(),
        project_id,
        name=forms.required(request.form, "name", "A name"),
        client=forms.text(request.form, "client"),
        budget_hours=forms.hours(request.form, "budget_hours"),
    )
    flash(f"Updated {project.id}.", "success")
    return redirect(url_for("projects.detail", project_id=project.id))


@bp.post("/<project_id>/rate")
def add_rate(project_id: str):
    """FR-14."""
    amount = forms.money(request.form, "rate", "a rate")
    if amount is None:
        flash("A rate is required.", "danger")
        return redirect(url_for("projects.detail", project_id=project_id))

    project = set_rate(storage(), project_id, amount, forms.day(request.form, "valid_from"))
    flash(
        f"{project.id} is {project.rates[-1].rate} an hour from {project.rates[-1].valid_from}.",
        "success",
    )
    return redirect(url_for("projects.detail", project_id=project_id))


@bp.post("/<project_id>/archive")
def archive(project_id: str):
    """FR-13."""
    if forms.flag(request.form, "undo"):
        project = unarchive_project(storage(), project_id)
        flash(f"Unarchived {project.id}.", "info")
    else:
        project = archive_project(storage(), project_id)
        flash(f"Archived {project.id}. Its entries and reports are untouched.", "info")
    return redirect(request.referrer or url_for("projects.detail", project_id=project_id))


@bp.post("/<project_id>/delete")
def delete(project_id: str):
    """FR-16."""
    project = remove_project(storage(), project_id)
    flash(f"Deleted {project.id}.", "info")
    return redirect(url_for("projects.index"))


@bp.post("/<project_id>/categories")
def add_category(project_id: str):
    """FR-44."""
    name = forms.required(request.form, "category", "A category")
    project = register_project_category(storage(), project_id, name)
    flash(f"{project.id} now suggests #{project.categories[-1]}.", "success")
    return redirect(url_for("projects.detail", project_id=project_id))


@bp.post("/<project_id>/categories/<name>/delete")
def remove_category(project_id: str, name: str):
    """FR-55: unregister only; entries keep the category they have."""
    unregister_project_category(storage(), project_id, name)
    flash(f"#{name} is no longer suggested for {project_id}.", "info")
    return redirect(url_for("projects.detail", project_id=project_id))


@bp.app_template_global()
def entry_project_name(projects_by_id: dict, project_id: str) -> str:
    project = projects_by_id.get(project_id)
    return project.name if project else f"{project_id} (unknown)"


@bp.post("/<project_id>/reset")
def reset_budget(project_id: str):
    """Clear the hour budget without having to blank a field."""
    project = edit_project(storage(), project_id, budget_hours=None)
    flash(f"Removed the budget on {project.id}.", "info")
    return redirect(url_for("projects.detail", project_id=project.id))
