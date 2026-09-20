"""Blueprints, one per page of the app."""

from __future__ import annotations

from flask import Blueprint

from cubit.web.views import dashboard, entries, projects, reports, settings


def blueprints() -> list[Blueprint]:
    """Every blueprint, in the order they appear in the navigation."""
    return [
        dashboard.bp,
        entries.bp,
        projects.bp,
        reports.bp,
        settings.bp,
    ]
