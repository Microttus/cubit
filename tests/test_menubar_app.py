"""FR-69: Quit Cubit closes the menu bar app, and only the menu bar app.

The rumps layer cannot be built without macOS, so these tests drive the quit
callback on a bare instance with stand-ins for rumps and the web server. No
test imports rumps (AGENT.md); what the menu *says* is tested in
``test_menubar_model.py``.
"""

from __future__ import annotations

import pytest

from cubit.core import CubitError, Storage, running_timer, start_timer
from cubit.menubar.app import CubitMenuBar


class FakeRumps:
    """The two rumps functions the quit path can reach."""

    def __init__(self) -> None:
        self.quits = 0
        self.notifications: list[tuple[str, str]] = []

    def quit_application(self) -> None:
        self.quits += 1

    def notification(self, _app: str, title: str, message: str) -> None:
        self.notifications.append((title, message))


class FakeWeb:
    """A web server that records its stop, and can fail it."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True
        if self.error is not None:
            raise self.error


def menu_bar(web: FakeWeb) -> CubitMenuBar:
    """An app with no macOS under it: enough for the quit path."""
    app = CubitMenuBar.__new__(CubitMenuBar)
    app.rumps = FakeRumps()
    app.web = web
    return app


def test_quit_stops_the_web_app_and_quits() -> None:
    app = menu_bar(FakeWeb())

    app._quit(None)

    assert app.web.stopped is True
    assert app.rumps.quits == 1


@pytest.mark.parametrize(
    "error",
    [RuntimeError("boom"), OSError("no such process"), CubitError("the folder is locked")],
    ids=["unexpected", "os", "cubit"],
)
def test_quit_happens_even_when_stopping_the_web_app_fails(error: Exception) -> None:
    """The bug this guards: guarded would swallow it and the app would stay up."""
    app = menu_bar(FakeWeb(error))

    app._quit(None)

    assert app.rumps.quits == 1, "Quit must not depend on the web app"


def test_a_failed_web_stop_does_not_look_like_a_broken_quit(caplog) -> None:
    """No 'Something went wrong' on the way out; the reason goes to the log."""
    app = menu_bar(FakeWeb(RuntimeError("boom")))

    app._quit(None)

    assert app.rumps.notifications == []
    assert "could not stop the web app" in caplog.text


def test_quitting_leaves_a_running_timer_running(storage: Storage) -> None:
    """FR-69: the timer lives in .state/timer.json, not in the app."""
    start_timer(storage, "acme-web", category="software-coding")
    app = menu_bar(FakeWeb())
    app.storage = storage

    app._quit(None)

    state = running_timer(storage)
    assert state is not None
    assert state.project_id == "acme-web"
