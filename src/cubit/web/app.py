"""The Flask application factory.

The web app is as thin as the CLI: it reads a form, calls :mod:`cubit.core`
and renders a template. Nothing here decides how cubit behaves, only how it
looks in a browser (AGENT.md rule 1).
"""

from __future__ import annotations

import os
from typing import Any

from flask import Flask, flash, redirect, render_template, request, url_for
from markupsafe import Markup, escape

from cubit.core import Config, CubitError, Storage, resolve_data_dir
from cubit.web import views
from cubit.web.filters import FILTERS
from cubit.web.security import FIELD_NAME, check_csrf, csrf_token

#: FR-30: the server listens on the loopback interface and nowhere else.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def create_app(data_dir: str | os.PathLike[str] | None = None) -> Flask:
    """Build the app over one cubit data folder."""
    storage = Storage(resolve_data_dir(data_dir))
    if not storage.exists:
        raise CubitError(
            f"No cubit data folder at {storage.data_dir}.",
            hint="Create one with 'cubit init', or point at another with --data-dir.",
        )

    app = Flask(__name__)
    app.config.update(
        CUBIT_STORAGE=storage,
        SECRET_KEY=storage.secret_key(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # Everything is served from this machine, so nothing needs caching.
        SEND_FILE_MAX_AGE_DEFAULT=0,
    )
    app.jinja_env.filters.update(FILTERS)
    # Globals, not context values: a macro imported with {% from %} sees these,
    # and every form needs the CSRF field.
    app.jinja_env.globals.update(csrf_token=csrf_token, csrf_input=_csrf_input)

    app.before_request(check_csrf)
    app.context_processor(lambda: _template_context(storage))
    app.register_error_handler(CubitError, _handle_cubit_error)

    for blueprint in views.blueprints():
        app.register_blueprint(blueprint)

    return app


def _template_context(storage: Storage) -> dict[str, Any]:
    """What every template can rely on: the config, the theme and a token."""
    try:
        config = storage.load_config()
    except CubitError:
        # A broken config.yaml must not take the whole app down; the page that
        # touches it will report the problem properly.
        config = Config()

    return {
        "config": config,
        "theme": config.theme,
        "currency": config.currency,
        "nav_active": request.blueprint or "",
    }


def _csrf_input() -> Markup:
    """The hidden field every form needs (FR-36)."""
    return Markup(f'<input type="hidden" name="{FIELD_NAME}" value="{escape(csrf_token())}">')


def _handle_cubit_error(error: CubitError):
    """Show a core error as a flash message rather than a stack trace (FR-25).

    A form post goes back where it came from so the page keeps its context; a
    plain page load gets an error page, because there is nowhere to go back to.
    """
    message = error.message if not error.hint else f"{error.message} {error.hint}"
    if request.method == "POST":
        flash(message, "danger")
        return redirect(request.referrer or url_for("dashboard.index"))
    return render_template("error.html", error=error, title="Something is wrong"), 400
