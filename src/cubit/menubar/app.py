"""The rumps layer: draw the menu model, and turn clicks into core calls.

This is the only module that imports rumps, and it is deliberately thin. It
decides nothing: :mod:`cubit.menubar.model` says what the menu contains, and
:mod:`cubit.core` does the work. What is left here is building NSMenuItems,
showing dialogs, and making sure no callback can ever take the app down
(FR-71, FR-73).
"""

from __future__ import annotations

import logging
import webbrowser
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any

from cubit.core import (
    CubitError,
    Storage,
    cancel_timer,
    normalize_category,
    start_timer,
    stop_timer,
)
from cubit.menubar.model import (
    NO_PROJECTS,
    CategoryChoice,
    Choice,
    Icon,
    MenuModel,
    build_menu,
)
from cubit.menubar.server import WebServer, dashboard_url

#: How long a click may wait for the folder lock. Long enough for a normal
#: write, short enough that the menu never feels stuck (FR-70).
LOCK_TIMEOUT = 2.0

#: How often the app re-reads the folder when nobody is looking (FR-70).
REFRESH_SECONDS = 30

ASSETS = Path(__file__).parent / "assets"
ICONS = {
    Icon.IDLE: ASSETS / "cubit-menubarTemplate.png",
    Icon.RUNNING: ASSETS / "cubit-menubar-runningTemplate.png",
}

log = logging.getLogger(__name__)


def guarded(method: Callable) -> Callable:
    """Never let a callback take the app down (FR-73).

    A menu bar app has no window to show a traceback in: an exception in a
    callback simply kills it. Anything a user could have caused becomes a
    notification, and anything else is logged and swallowed.
    """

    @wraps(method)
    def wrapper(self: CubitMenuBar, *args: Any, **kwargs: Any) -> Any:
        try:
            return method(self, *args, **kwargs)
        except CubitError as error:
            log.warning("%s", error.message)
            self.notify(error.message, error.hint or "")
        except Exception:
            log.exception("unexpected error in %s", method.__name__)
            self.notify("Something went wrong", "See the log, or run 'cubit check'.")
        return None

    return wrapper


class CubitMenuBar:
    """The menu bar app (FR-63)."""

    def __init__(self, data_dir: Path, port: int) -> None:
        import rumps

        self.rumps = rumps
        self.storage = Storage(data_dir, lock_timeout=LOCK_TIMEOUT)
        self.web = WebServer(port=port, data_dir=data_dir)
        self.model = MenuModel()

        self.app = rumps.App("Cubit", title="", quit_button=None)
        self.app.template = True
        self._hide_from_dock()

        self._timer = rumps.Timer(self._tick, REFRESH_SECONDS)
        self._timer.start()
        self._delegate = None
        self._watch_menu_opening()

    # ------------------------------------------------------------- running

    def run(self) -> None:
        self.refresh()
        self.app.run()

    def _hide_from_dock(self) -> None:
        """No Dock icon, whichever way the app was started (FR-63)."""
        try:
            from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

            NSApplication.sharedApplication().setActivationPolicy_(
                NSApplicationActivationPolicyAccessory
            )
        except Exception:  # pragma: no cover - only on a broken PyObjC
            log.debug("could not set the activation policy", exc_info=True)

    @guarded
    def _tick(self, _timer: Any) -> None:
        self.refresh()

    @guarded
    def _menu_opened(self, _sender: Any = None) -> None:
        self.refresh()

    def _watch_menu_opening(self) -> None:
        """Refresh the moment the menu is clicked, not up to 30s later (FR-70).

        rumps has no hook for this, so the NSMenu gets a delegate. It reaches
        into rumps to find that menu, so it is wrapped: if a future rumps moves
        it, the app still works and the timer still refreshes, just not
        instantly.
        """
        try:
            from Foundation import NSObject

            menu = getattr(self.app.menu, "_menu", None)
            if menu is None:  # pragma: no cover - only on a changed rumps
                log.debug("could not find the NSMenu to watch")
                return

            outer = self

            class _MenuWatcher(NSObject):
                def menuWillOpen_(self, _menu: Any) -> None:  # noqa: N802
                    outer._menu_opened()

            self._delegate = _MenuWatcher.alloc().init()
            menu.setDelegate_(self._delegate)
        except Exception:  # pragma: no cover - not macOS, or a changed rumps
            log.debug("could not watch the menu opening", exc_info=True)

    def refresh(self) -> None:
        """Re-read the folder and redraw the menu.

        Reads never take the lock, so this cannot block on another process
        writing; a folder that will not parse comes back as an error model.
        """
        self.model = build_menu(self.storage)
        self._render()

    # ------------------------------------------------------------ drawing

    def _render(self) -> None:
        model = self.model
        self.app.title = model.title
        icon = ICONS.get(model.icon)
        if icon is not None and icon.exists():
            self.app.icon = str(icon)
            self.app.template = True

        self.app.menu.clear()
        self.app.menu.update(self._items(model))

    def _items(self, model: MenuModel) -> list[Any]:
        rumps = self.rumps
        items: list[Any] = []

        if model.error:
            items.append(rumps.MenuItem(model.error, callback=self._open_dashboard))
            items.append(rumps.separator)
            items.extend(self._footer())
            return items

        if model.running is not None:
            items.append(rumps.MenuItem(model.running.heading))
            items.append(rumps.MenuItem(model.running.detail))
            items.append(rumps.MenuItem("Stop timer...", callback=self._stop))
            items.append(rumps.MenuItem("Cancel timer", callback=self._cancel))
        else:
            items.append(self._start_menu(model))

        items.append(rumps.separator)
        items.append(rumps.MenuItem(f"Today{_pad(model.today_text)}"))
        items.append(rumps.MenuItem(f"This week{_pad(model.week_text)}"))
        items.append(rumps.separator)
        items.extend(self._footer())
        return items

    def _footer(self) -> list[Any]:
        rumps = self.rumps
        return [
            rumps.MenuItem("Open dashboard", callback=self._open_dashboard),
            rumps.MenuItem("Quit Cubit", callback=self._quit),
        ]

    def _start_menu(self, model: MenuModel) -> Any:
        """The Start timer submenu of projects and their categories (FR-65)."""
        rumps = self.rumps
        start = rumps.MenuItem("Start timer")
        if not model.has_projects:
            start.add(rumps.MenuItem(NO_PROJECTS))
            return start

        for project in model.projects:
            entry = rumps.MenuItem(project.label)
            for choice in project.categories:
                entry.add(
                    rumps.MenuItem(
                        choice.label,
                        callback=self._starter(project.project_id, choice),
                    )
                )
            start.add(entry)
        return start

    # ----------------------------------------------------------- callbacks

    def _starter(self, project_id: str, choice: CategoryChoice) -> Callable:
        @guarded
        def start(app: CubitMenuBar, _sender: Any) -> None:
            category = choice.category
            if choice.kind is Choice.NEW:
                typed = app.ask("New category", "Category name, without the #", "")
                if typed is None or not typed.strip():
                    return
                category = normalize_category(typed)
            elif choice.kind is Choice.NONE:
                category = None

            start_timer(app.storage, project_id, category=category)
            app.refresh()

        return lambda sender: start(self, sender)

    @guarded
    def _stop(self, _sender: Any) -> None:
        """Stop, asking for a note first, prefilled with the timer's (FR-66)."""
        note = self.ask("Stop timer", "Note (optional)", self._current_note())
        if note is None:
            return
        entry = stop_timer(self.storage, note=note)
        self.notify("Logged", f"{entry.duration_minutes} minutes to {entry.project_id}")
        self.refresh()

    def _current_note(self) -> str:
        state = self.storage.read_timer()
        return state.note if state else ""

    @guarded
    def _cancel(self, _sender: Any) -> None:
        """Drop the timer without logging anything (FR-4)."""
        state = cancel_timer(self.storage)
        self.notify("Timer cancelled", f"Nothing was logged for {state.project_id}.")
        self.refresh()

    @guarded
    def _open_dashboard(self, _sender: Any) -> None:
        """Open the web app, starting one if nothing answers (FR-68)."""
        if not self.web.ensure_running():
            self.notify("Cannot open the dashboard", "Try 'cubit web' in a terminal.")
            return
        webbrowser.open(dashboard_url(self.web.port))

    @guarded
    def _quit(self, _sender: Any) -> None:
        """Close the menu bar app only. A running timer keeps running (FR-69)."""
        self.web.stop()
        self.rumps.quit_application()

    # ------------------------------------------------------------ dialogs

    def ask(self, title: str, message: str, default: str = "") -> str | None:
        """A small text dialog. ``None`` when the user cancels."""
        window = self.rumps.Window(
            title=title,
            message=message,
            default_text=default,
            ok="OK",
            cancel="Cancel",
            dimensions=(260, 22),
        )
        response = window.run()
        return response.text if response.clicked else None

    def notify(self, title: str, message: str) -> None:
        """Tell the user something (FR-73).

        A notification needs an app bundle, which cubit does not have when it
        is started from a terminal, so the log is the path that always works
        and the notification is a bonus.
        """
        log.info("%s: %s", title, message)
        try:
            self.rumps.notification("Cubit", title, message)
        except Exception:  # pragma: no cover - no bundle identifier
            log.debug("could not post a notification", exc_info=True)


def _pad(value: str, width: int = 12) -> str:
    """Right-align a total after its label, the way the spec draws the menu."""
    return value.rjust(width)


def run(data_dir: Path, port: int) -> None:
    """Start the menu bar app. Only ever called on macOS, with rumps present."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    CubitMenuBar(data_dir, port).run()
