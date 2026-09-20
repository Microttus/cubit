"""The settings page: config.yaml, edited in a form (FR-78).

``config.yaml`` is meant to be edited by hand, and still is. This is the same
six settings in a browser, saved through the same round-tripping write, so the
comments and the hand-written key order in the file survive being saved here.
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from pydantic import ValidationError

from cubit.core import Config, CubitError
from cubit.web import forms
from cubit.web.views._shared import storage

bp = Blueprint("settings", __name__, url_prefix="/settings")

THEMES = ("dark", "light", "auto")
WEEK_STARTS = ("monday", "sunday")
MENUBAR_TITLES = ("none", "time", "project-time")


@bp.get("/")
def index():
    store = storage()
    return render_template(
        "settings.html",
        title="Settings",
        settings=store.load_config(),
        themes=THEMES,
        week_starts=WEEK_STARTS,
        menubar_titles=MENUBAR_TITLES,
        config_path=store.config_path,
        data_dir=store.data_dir,
    )


@bp.post("/")
def save():
    """Write every setting at once (FR-78).

    The whole config is validated as one before anything is written, so a bad
    value leaves the file exactly as it was rather than half-updated.
    """
    store = storage()
    wanted = {
        "currency": forms.required(request.form, "currency", "A currency"),
        "week_starts_on": forms.text(request.form, "week_starts_on", "monday"),
        "budget_warning_percent": forms.whole(
            request.form, "budget_warning_percent", "The budget warning"
        ),
        "prompt_for_category": forms.flag(request.form, "prompt_for_category"),
        "theme": forms.text(request.form, "theme", "dark"),
        "menubar_title": forms.text(request.form, "menubar_title", "time"),
    }

    store.save_config(_validated(wanted))
    flash("Settings saved.", "success")
    return redirect(url_for("settings.index"))


@bp.post("/theme")
def set_theme():
    """The header toggle: one setting, from wherever the user happens to be.

    The choice is a setting, not a browser preference, so it goes into
    ``config.yaml`` where the CLI and the next session can see it too (FR-62).
    """
    wanted = forms.required(request.form, "theme", "A theme").lower()
    if wanted not in THEMES:
        raise CubitError(
            f"Unknown theme {wanted!r}.",
            hint=f"Choose one of {', '.join(THEMES)}.",
        )

    store = storage()
    config = store.load_config()
    store.save_config(config.model_copy(update={"theme": wanted}))
    return redirect(request.referrer or url_for("dashboard.index"))


def _validated(values: dict) -> Config:
    """Turn the form into a Config, or explain what is wrong with it."""
    try:
        return Config.model_validate(values)
    except ValidationError as error:
        first = error.errors()[0]
        field = ".".join(str(part) for part in first["loc"]) or "a setting"
        message = first["msg"].removeprefix("Value error, ")
        raise CubitError(
            f"{field}: {message}",
            hint="Check the value and try again; nothing was saved.",
        ) from None
