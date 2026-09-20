"""The dashboard: the timer, today's entries and this week's total (FR-31)."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from cubit import __version__
from cubit.core import (
    cancel_timer,
    elapsed_minutes,
    find_entries,
    running_timer,
    start_timer,
    stop_timer,
    summarize,
    week_bounds,
)
from cubit.web import forms
from cubit.web.views._shared import category_suggestions, pickable_projects, storage, today

bp = Blueprint("dashboard", __name__)


@bp.get("/")
def index():
    store = storage()
    config = store.load_config()
    timer = running_timer(store)
    now = today()

    week_start, week_end = week_bounds(now, config.week_starts_on)
    week = summarize(
        find_entries(store, start=week_start, end=week_end),
        store.load_projects_map(),
        start=week_start,
        end=week_end,
        week_starts_on=config.week_starts_on,
        fill_days=True,
    )
    todays = [entry for entry in week.entries if entry.date == now]

    projects = pickable_projects(store, include=timer.project_id if timer else None)
    return render_template(
        "dashboard.html",
        title="Dashboard",
        timer=timer,
        elapsed=elapsed_minutes(timer) if timer else 0,
        projects=projects,
        suggestions=category_suggestions(store, projects),
        projects_by_id=store.load_projects_map(),
        today=now,
        todays_entries=todays,
        todays_minutes=sum(entry.duration_minutes for entry in todays),
        week=week,
    )


@bp.get("/healthz")
def healthz():
    """Say that this port is a cubit web app (FR-68).

    The menu bar app probes this before opening the dashboard, so it does not
    hand the browser to whatever else happens to be on port 8000. A plain GET,
    so the CSRF guard does not apply, and it reveals nothing: the name and the
    version, no data.
    """
    return {"app": "cubit", "version": __version__, "status": "ok"}


@bp.post("/timer/start")
def start():
    """FR-1."""
    store = storage()
    start_timer(
        store,
        forms.required(request.form, "project_id", "A project"),
        category=forms.optional(request.form, "category"),
        note=forms.text(request.form, "note"),
        force=forms.flag(request.form, "force"),
    )
    return redirect(url_for("dashboard.index"))


@bp.post("/timer/stop")
def stop():
    """FR-2."""
    entry = stop_timer(
        storage(),
        note=forms.optional(request.form, "note"),
        category=forms.optional(request.form, "category"),
    )
    flash(f"Logged {entry.duration_minutes} minutes to {entry.project_id}.", "success")
    return redirect(url_for("dashboard.index"))


@bp.post("/timer/cancel")
def cancel():
    """FR-4."""
    state = cancel_timer(storage())
    flash(f"Cancelled the timer on {state.project_id}. Nothing was logged.", "info")
    return redirect(url_for("dashboard.index"))
