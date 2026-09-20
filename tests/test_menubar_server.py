"""FR-68: finding, or starting, the web app the menu bar opens.

The probe is exercised against a real Flask test server on a real port, so the
health check is proved end to end rather than against a mock.
"""

from __future__ import annotations

import http.server
import json
import threading
from pathlib import Path

import pytest

from cubit.menubar.server import (
    HEALTH_APP,
    WebServer,
    dashboard_url,
    health_url,
    is_cubit_running,
)


def free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Answering(http.server.BaseHTTPRequestHandler):
    """A stand-in server whose /healthz answer the tests set."""

    payload: bytes = b'{"app": "cubit"}'
    status: int = 200

    def do_GET(self) -> None:  # noqa: N802 - the stdlib spells it this way
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def serving():
    """Start a throwaway HTTP server and give the test its port."""
    servers = []

    def start(payload: bytes = b'{"app": "cubit"}', status: int = 200) -> int:
        handler = type("Handler", (Answering,), {"payload": payload, "status": status})
        server = http.server.HTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return server.server_port

    yield start
    for server in servers:
        server.shutdown()


def test_the_urls() -> None:
    assert health_url(8000) == "http://127.0.0.1:8000/healthz"
    assert dashboard_url(8000) == "http://127.0.0.1:8000/"


def test_a_cubit_on_the_port_is_recognised(serving) -> None:
    assert is_cubit_running(serving()) is True


def test_a_closed_port_is_not_cubit() -> None:
    assert is_cubit_running(free_port()) is False


def test_something_else_on_the_port_is_not_cubit(serving) -> None:
    """The point of /healthz: do not hand the browser to a stranger."""
    assert is_cubit_running(serving(b'{"app": "grafana"}')) is False


def test_a_port_answering_with_html_is_not_cubit(serving) -> None:
    assert is_cubit_running(serving(b"<html>hello</html>")) is False


def test_a_port_answering_with_a_json_list_is_not_cubit(serving) -> None:
    assert is_cubit_running(serving(b"[1, 2, 3]")) is False


def test_an_error_status_is_not_cubit(serving) -> None:
    assert is_cubit_running(serving(b'{"app": "cubit"}', status=500)) is False


def test_the_real_web_app_answers_the_probe(web_app) -> None:
    """FR-68: the route the probe relies on is the one the app serves."""
    response = web_app.test_client().get("/healthz")
    payload = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert payload["app"] == HEALTH_APP
    assert payload["status"] == "ok"
    assert payload["version"]


def test_the_probe_needs_no_csrf_token(web_app) -> None:
    """It is a GET, so the guard does not apply (FR-36)."""
    assert web_app.test_client().get("/healthz").status_code == 200


def test_the_probe_gives_away_no_data(web_app) -> None:
    body = web_app.test_client().get("/healthz").get_data(as_text=True)
    for secret in ["acme", "Acme", "entries", "projects"]:
        assert secret not in body


def test_a_server_that_is_already_running_is_not_started_again(serving) -> None:
    """FR-68: one the user started themselves is left alone."""
    server = WebServer(port=serving())

    assert server.ensure_running() is True
    assert server.process is None
    assert server.started_by_us is False


def test_stopping_a_server_we_did_not_start_does_nothing(serving) -> None:
    server = WebServer(port=serving())
    server.ensure_running()

    server.stop()  # must not raise, and must not kill anything

    assert is_cubit_running(server.port) is True


def test_starting_and_stopping_a_real_web_app(sample_dir: Path) -> None:
    """The whole of FR-68, with a real cubit web subprocess."""
    port = free_port()
    server = WebServer(port=port, data_dir=sample_dir)
    assert is_cubit_running(port) is False

    try:
        assert server.ensure_running() is True, "the web app did not come up"
        assert server.started_by_us is True
        assert is_cubit_running(port) is True
    finally:
        server.stop()

    assert server.process is None
    assert is_cubit_running(port) is False


def test_ensure_running_is_idempotent(sample_dir: Path) -> None:
    port = free_port()
    server = WebServer(port=port, data_dir=sample_dir)
    try:
        assert server.ensure_running() is True
        first = server.process
        assert server.ensure_running() is True
        assert server.process is first  # not a second server
    finally:
        server.stop()


def test_the_command_carries_the_data_folder(tmp_path: Path) -> None:
    """The menu bar and the web app it starts must share one folder."""
    command = WebServer(port=8000, data_dir=tmp_path)._command()

    assert command is not None
    assert "--data-dir" in command
    assert str(tmp_path) in command
    assert command[-3:] == ["web", "--port", "8000"]
