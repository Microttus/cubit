"""FR-36 and FR-35: CSRF protection, and no reaching outside this machine."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from cubit.core import CubitError, Storage
from cubit.web import DEFAULT_HOST, DEFAULT_PORT, create_app
from cubit.web.security import UNSAFE_METHODS
from helpers import forms_in, text_of

#: Every route that changes something, with the least it needs to work.
MUTATIONS = [
    ("/timer/start", {"project_id": "acme-web"}),
    ("/timer/stop", {}),
    ("/timer/cancel", {}),
    ("/entries/", {"project_id": "acme-web", "duration": "1h", "date": "2026-09-21"}),
    ("/entries/a3f9c1", {"project_id": "acme-web", "duration": "1h", "date": "2026-09-21"}),
    ("/entries/a3f9c1/delete", {}),
    ("/projects/", {"id": "beta-app", "name": "Beta app"}),
    ("/projects/acme-web", {"name": "Acme website"}),
    ("/projects/acme-web/rate", {"rate": "120"}),
    ("/projects/acme-web/archive", {}),
    ("/projects/acme-web/categories", {"category": "invoicing"}),
    ("/settings/theme", {"theme": "light"}),
]


@pytest.mark.parametrize(("path", "data"), MUTATIONS, ids=lambda value: str(value)[:40])
def test_every_post_needs_a_token(web, path: str, data: dict) -> None:
    """FR-36: without this, any page open in the browser could post here."""
    assert web.raw.post(path, data=data).status_code == 400


@pytest.mark.parametrize(("path", "data"), MUTATIONS, ids=lambda value: str(value)[:40])
def test_every_post_works_with_a_token(web, path: str, data: dict) -> None:
    assert web.post(path, data).status_code == 200


def test_a_token_from_another_session_is_refused(web, web_app) -> None:
    """A token has to belong to the session that sends it."""
    other = web_app.test_client()
    stolen = re.search(
        r'name="csrf_token" value="([^"]+)"', other.get("/").get_data(as_text=True)
    ).group(1)

    assert web.raw.post("/timer/cancel", data={"csrf_token": stolen}).status_code == 400


def test_a_tampered_token_is_refused(web) -> None:
    good = web.token()
    bad = good[:-1] + ("a" if good[-1] != "a" else "b")
    assert web.raw.post("/timer/cancel", data={"csrf_token": bad}).status_code == 400


def test_an_empty_token_is_refused(web) -> None:
    assert web.raw.post("/timer/cancel", data={"csrf_token": ""}).status_code == 400


def test_get_requests_need_no_token(web) -> None:
    """Reading a page must never be blocked by the guard."""
    for path in ["/", "/entries/", "/projects/", "/reports/"]:
        assert web.raw.get(path).status_code == 200


def test_the_unsafe_methods_are_the_ones_that_change_things() -> None:
    assert set(UNSAFE_METHODS) == {"POST", "PUT", "PATCH", "DELETE"}


def test_every_form_carries_a_token(web) -> None:
    """A form without the field would fail the moment it is submitted."""
    for path in ["/", "/entries/", "/entries/new", "/projects/new", "/projects/acme-web"]:
        html = text_of(web.get(path))
        for form in forms_in(html):
            if 'method="post"' in form:
                assert 'name="csrf_token"' in form, f"{path}: a form has no token"


def test_the_session_cookie_is_locked_down(web_app) -> None:
    assert web_app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert web_app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert web_app.config["SECRET_KEY"]


def test_the_secret_key_survives_a_restart(sample_dir: Path) -> None:
    """A form open in the browser must still work after the server comes back."""
    first = create_app(sample_dir).config["SECRET_KEY"]
    second = create_app(sample_dir).config["SECRET_KEY"]
    assert first == second


def test_the_secret_key_is_kept_out_of_the_synced_data(sample_dir: Path) -> None:
    create_app(sample_dir)
    store = Storage(sample_dir)
    assert store.secret_key_path.parent.name == ".state"
    assert oct(store.secret_key_path.stat().st_mode)[-3:] == "600"


def test_pages_ask_for_nothing_outside_this_machine(web) -> None:
    """FR-35: the app works offline."""
    for path in ["/", "/entries/", "/projects/", "/projects/acme-web", "/reports/"]:
        html = text_of(web.get(path))
        assert "http://" not in html
        assert "https://" not in html
        assert "//cdn" not in html


def test_the_stylesheet_and_script_are_local(web) -> None:
    for asset in ["/static/theme.css", "/static/app.css", "/static/app.js"]:
        response = web.get(asset)
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "http://" not in body and "https://" not in body


def test_the_server_defaults_to_the_loopback_interface() -> None:
    """FR-30."""
    assert DEFAULT_HOST == "127.0.0.1"
    assert DEFAULT_PORT == 8000


def test_the_cli_offers_the_same_defaults(cli) -> None:
    """The web command's defaults must not drift from the app's."""
    help_text = cli("web", "--help").stdout
    assert DEFAULT_HOST in help_text
    assert str(DEFAULT_PORT) in help_text


def test_creating_an_app_without_a_data_folder_explains_itself(tmp_path: Path) -> None:
    with pytest.raises(CubitError) as caught:
        create_app(tmp_path / "nothing-here")
    assert "cubit init" in (caught.value.hint or "")
