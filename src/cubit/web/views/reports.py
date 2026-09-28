"""The reports page: weekly, monthly, per-project, per-client, per-category (FR-34)."""

from __future__ import annotations

import re

from flask import Blueprint, Response, render_template, request

from cubit.core import (
    CubitError,
    category_document,
    category_report,
    client_document,
    client_report,
    find_entries,
    project_document,
    project_report,
    render_file,
    resolve_period,
    summarize,
    summary_document,
    with_title,
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
        "billing": forms.text(request.args, "billing", "all"),
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
            find_entries(
                store, start=start, end=end, category=category, billed=forms.billing(request.args)
            ),
            store.load_projects_map(),
            start=start,
            end=end,
            week_starts_on=config.week_starts_on,
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
        billed=forms.billing(request.args),
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
            find_entries(
                store,
                category=forms.optional(request.args, "category"),
                billed=forms.billing(request.args),
            ),
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
            find_entries(store, billed=forms.billing(request.args)),
            store.load_projects_map(),
            start=start,
            end=end,
        ),
        "chosen": chosen,
        "start": start,
        "end": end,
        "projects_by_id": store.load_projects_map(),
    }


@bp.app_template_global()
def export_fields() -> list[tuple[str, str]]:
    """The query string of the report on screen, for the download form (FR-23).

    The form sends these back as hidden fields, so a download always matches
    what is displayed. The title and the format come from the form itself.
    """
    args = {key: value for key, value in request.args.items() if key not in {"title", "format"}}
    args.setdefault("view", "week")
    return list(args.items())


#: What a downloaded report is called and served as.
EXPORTS = {
    "csv": ("csv", "text/csv"),
    "markdown": ("md", "text/markdown"),
    "pdf": ("pdf", "application/pdf"),
}


@bp.get("/export")
def export():
    """Download the report on screen as CSV, Markdown or PDF (FR-23, FR-80).

    The query string is the same one the page uses, so the link can simply
    carry it over and the download always matches what is displayed.
    """
    fmt = forms.text(request.args, "format", "csv")
    if fmt not in EXPORTS:
        raise CubitError(
            f"Cannot export as {fmt!r}.",
            hint=f"Use one of {', '.join(EXPORTS)}.",
        )

    store = storage()
    config = store.load_config()
    kind = forms.text(request.args, "view", "week")
    if kind not in VIEWS:
        kind = "week"

    document = _document(store, config, kind)
    if document is None:
        raise CubitError("There is nothing to export yet.", hint="Pick a report first.")
    document = with_title(document, forms.optional(request.args, "title"))

    extension, media_type = EXPORTS[fmt]
    name = f"cubit-{kind}-{_slug(document.title)}.{extension}"
    return Response(
        render_file(document, fmt, generated=today()),
        mimetype=media_type,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


def _document(store, config, kind: str):
    """The report the query string describes, as an exportable document."""
    if kind in {"week", "month"}:
        context = _summary(store, config, kind)
        return summary_document(
            context["summary"],
            kind=kind,
            label=context["period_label"],
            currency=config.currency,
            projects=store.load_projects_map(),
            entries=True,
        )

    if kind == "project":
        context = _project(store, config, store.load_projects())
        if context["report"] is None:
            return None
        return project_document(
            context["report"],
            currency=config.currency,
            projects=store.load_projects_map(),
        )

    if kind == "client":
        context = _client(store)
        if context["report"] is None:
            return None
        return client_document(context["report"], currency=config.currency)

    context = _category(store)
    if context["report"] is None:
        return None
    return category_document(context["report"], currency=config.currency)


def _slug(title: str) -> str:
    """A filename-safe version of the report's title."""
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "report"
