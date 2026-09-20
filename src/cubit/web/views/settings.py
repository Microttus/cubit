"""Small state changes that are not a page of their own: the theme toggle."""

from __future__ import annotations

from flask import Blueprint, redirect, request, url_for

from cubit.core import CubitError
from cubit.web import forms
from cubit.web.views._shared import storage

bp = Blueprint("settings", __name__)

THEMES = ("dark", "light", "auto")


@bp.post("/theme")
def set_theme():
    """Switch between the dark and light "ice" themes (FR-62).

    The choice is a setting, not a browser preference, so it goes into
    ``config.yaml`` where the CLI and the next session can see it too.
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
