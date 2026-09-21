"""Finding, or starting, the web app the menu bar opens (FR-68).

"Open dashboard" should just work, whether the web app is already running,
was started by the CLI in another terminal, or is not running at all. The menu
bar app asks the port whether it is Cubit, starts one if nothing answers, and
only stops a server it started itself.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

#: What ``/healthz`` answers with, so a stranger on the port is not mistaken
#: for the web app (FR-68).
HEALTH_APP = "cubit"

#: Seconds to wait for the port to answer. A local server answers at once;
#: anything slower is not worth making the user wait for.
PROBE_TIMEOUT = 0.6

#: How long to give a server we just started before giving up on it.
STARTUP_TIMEOUT = 10.0

log = logging.getLogger(__name__)


def health_url(port: int, host: str = "127.0.0.1") -> str:
    return f"http://{host}:{port}/healthz"


def dashboard_url(port: int, host: str = "127.0.0.1") -> str:
    return f"http://{host}:{port}/"


def is_cubit_running(port: int, *, timeout: float = PROBE_TIMEOUT) -> bool:
    """True when the thing answering on ``port`` is a cubit web app.

    A closed port, a timeout, something that is not JSON and something that is
    JSON but not cubit all mean the same thing here: we cannot use it.
    """
    try:
        with urllib.request.urlopen(health_url(port), timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return False
    return isinstance(payload, dict) and payload.get("app") == HEALTH_APP


@dataclass
class WebServer:
    """The web app the menu bar opens, and whether we are the one running it."""

    port: int
    data_dir: Path | None = None
    process: subprocess.Popen | None = None

    @property
    def started_by_us(self) -> bool:
        return self.process is not None

    def ensure_running(self, *, wait: float = STARTUP_TIMEOUT) -> bool:
        """Make sure a cubit web app is on the port. True if one is.

        A server that is already there is left alone, so quitting the menu bar
        app never takes down a server the user started themselves (FR-68).
        """
        if is_cubit_running(self.port):
            return True
        if self.process is not None and self.process.poll() is None:
            return _wait_until_healthy(self.port, wait)

        command = self._command()
        if command is None:
            log.error("cannot find the cubit executable to start the web app")
            return False

        log.info("starting the web app: %s", " ".join(command))
        try:
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            log.exception("could not start the web app")
            self.process = None
            return False

        if _wait_until_healthy(self.port, wait):
            return True

        log.error("the web app did not answer on port %s", self.port)
        self.stop()
        return False

    def stop(self) -> None:
        """Stop the web app, but only if we started it (FR-68)."""
        process = self.process
        self.process = None
        if process is None or process.poll() is not None:
            return

        log.info("stopping the web app we started")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - a stuck server
            process.kill()

    def _command(self) -> list[str] | None:
        """How to start a second cubit, from wherever this one is running.

        Inside the macOS app bundle there is no ``cubit`` on the PATH a GUI app
        inherits, and ``-m`` does not work on a frozen executable, so the
        bundle starts the web app by running itself with ``web`` after it
        (FR-79). ``launcher.py`` is what makes that mean the CLI.
        """
        if getattr(sys, "frozen", False):
            command = [sys.executable]
        else:
            executable = shutil.which("cubit")
            command = [executable] if executable else [sys.executable, "-m", "cubit.cli.main"]
            if executable is None and not Path(sys.executable).exists():  # pragma: no cover
                return None
        if self.data_dir is not None:
            command += ["--data-dir", str(self.data_dir)]
        return [*command, "web", "--port", str(self.port)]


def _wait_until_healthy(port: int, wait: float) -> bool:
    import time

    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if is_cubit_running(port):
            return True
        time.sleep(0.2)
    return False
