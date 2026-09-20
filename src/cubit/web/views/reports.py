"""The reports page: weekly, monthly, per-project, per-client, per-category (FR-34)."""

from __future__ import annotations

from flask import Blueprint, render_template, request

from cubit.core import (
    category_report,
    client_report,
    find_entries,
    project_report,
    resolve_period,
    summarize,
)
from cubit.web import forms
from cubit.web.views._shared import storage, today

bp = Blueprint("reports", __name__, url_prefix="/reports")

VIEWS = ("week", "month", "project", "client", "category")


@bp.get("/")
def index():
    store = storage()
    config = store.load_config()
    kind = forms.text(request.args, "view", "week")
    if kind not in VIEWS:
        kind = "week"

    projects = store.load_projects()
    context = {
        "title": "Reports",
        "kind": kind,
        "views": VIEWS,
        "projects": projects,
        "clients": sorted({project.client for project in projects if project.client}),
        "categories": sorted({name for project in projects for name in project.categories}),
        "today": today(),
    }

    if kind in {"week", "month"}:
        context.update(_summary(store, config, kind))
    elif kind == "project":
        context.update(_project(store, config, projects))
    elif kind == "client":
        context.update(_client(store))
    else:
        context.update(_category(store))

    return render_template("reports.html", **context)


def _range() -> tuple[object, object]:
    """The custom range from the query string, if any (FR-21)."""
    return forms.day(request.args, "from"), forms.day(request.args, "to")


def _summary(store, config, kind: str) -> dict:
    """FR-17, FR-18: a week or a month, or a custom range over either."""
    custom_start, custom_end = _range()
    when = forms.text(request.args, "when", "this")

    if custom_start and custom_end:
        start, end, label = custom_start, custom_end, "Custom range"
    else:
        start, end = resolve_period(kind, when, week_starts_on=config.week_starts_on)
        label = (
            f"Week {start.isocalendar().week}, {start.year}"
            if kind == "week"
            else start.strftime("%B %Y")
        )

    category = forms.optional(request.args, "category")
    return {
        "summary": summarize(
            find_entries(store, start=start, end=end, category=category),
            store.load_projects_map(),
            start=start,
            end=end,
            week_starts_on=config.week_starts_on,
            fill_days=(kind == "week"),
        ),
        "period_label": label,
        "start": start,
        "end": end,
        "when": when,
        "category": category,
        "projects_by_id": store.load_projects_map(),
    }


def _project(store, config, projects) -> dict:
    """FR-19: the project report, with its budget."""
    chosen = forms.optional(request.args, "project")
    if chosen is None and projects:
        chosen = projects[0].id
    if chosen is None:
        return {"report": None, "chosen": None, "start": None, "end": None}

    start, end = _range()
    # The whole history: a project's total and its budget are not about the period.
    report = project_report(
        store.get_project(chosen),
        find_entries(store, category=forms.optional(request.args, "category")),
        store.load_projects_map(),
        start=start,
        end=end,
        warning_percent=config.budget_warning_percent,
    )
    return {"report": report, "chosen": chosen, "start": start, "end": end}


def _client(store) -> dict:
    """FR-20."""
    projects = store.load_projects()
    clients = sorted({project.client for project in projects if project.client})
    chosen = forms.optional(request.args, "client") or (clients[0] if clients else None)
    if chosen is None:
        return {"report": None, "chosen": None, "start": None, "end": None}

    start, end = _range()
    return {
        "report": client_report(
            chosen,
            find_entries(store, category=forms.optional(request.args, "category")),
            store.load_projects_map(),
            start=start,
            end=end,
        ),
        "chosen": chosen,
        "start": start,
        "end": end,
        "projects_by_id": store.load_projects_map(),
    }


def _category(store) -> dict:
    """FR-61: one category across every project that uses it."""
    chosen = forms.optional(request.args, "category")
    if chosen is None:
        return {"report": None, "chosen": None, "start": None, "end": None}

    start, end = _range()
    return {
        "report": category_report(
            chosen,
            find_entries(store),
            store.load_projects_map(),
            start=start,
            end=end,
        ),
        "chosen": chosen,
        "start": start,
        "end": end,
        "projects_by_id": store.load_projects_map(),
    }
