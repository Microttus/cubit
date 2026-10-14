"""Shared fixtures. Tests never touch a real data folder: they copy the sample
folder in ``tests/fixtures/`` into ``tmp_path`` (AGENT.md)."""

from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path

import pytest
from click.testing import Result
from typer.testing import CliRunner

from cubit.cli.main import app
from cubit.core import Storage

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_DATA = FIXTURES / "sample-data"


@pytest.fixture(autouse=True, scope="session")
def _oslo_time():
    """Run in Europe/Oslo, whatever the machine's zone: the timer and menu bar
    tests build Oslo times and read them back as local time."""
    previous = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/Oslo"
    time.tzset()
    yield
    if previous is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = previous
    time.tzset()


@pytest.fixture
def sample_dir(tmp_path: Path) -> Path:
    """A writable copy of the sample data folder."""
    target = tmp_path / "cubit-data"
    shutil.copytree(SAMPLE_DATA, target)
    return target


@pytest.fixture
def storage(sample_dir: Path) -> Storage:
    """Storage over the sample data."""
    return Storage(sample_dir)


@pytest.fixture
def empty_storage(tmp_path: Path) -> Storage:
    """Storage over a freshly initialised, empty data folder."""
    store = Storage(tmp_path / "empty-data")
    store.init()
    return store


@pytest.fixture
def runner() -> CliRunner:
    """A Typer runner with colour off, so assertions see plain text."""
    return CliRunner(env={"NO_COLOR": "1"})


@pytest.fixture
def cli(runner: CliRunner, sample_dir: Path):
    """Run cubit against the sample data folder and return the result."""

    def invoke(*args: str, input: str | None = None) -> Result:
        return runner.invoke(app, ["--data-dir", str(sample_dir), *args], input=input)

    return invoke


@pytest.fixture
def cli_empty(runner: CliRunner, tmp_path: Path):
    """Run cubit against a folder that has not been initialised yet."""
    data_dir = tmp_path / "fresh"

    def invoke(*args: str, input: str | None = None) -> Result:
        return runner.invoke(app, ["--data-dir", str(data_dir), *args], input=input)

    invoke.data_dir = data_dir  # type: ignore[attr-defined]
    return invoke


@pytest.fixture
def web_app(sample_dir: Path):
    """A Flask app over a copy of the sample data folder."""
    from cubit.web import create_app

    app = create_app(sample_dir)
    app.config.update(TESTING=True)
    return app


@pytest.fixture
def web(web_app):
    """A test client that carries the CSRF token for you.

    ``web.post`` adds the session's token, so tests exercise the flows rather
    than the plumbing; ``web.raw`` posts without one, for the CSRF tests.
    """
    client = web_app.test_client()

    class Browser:
        raw = client

        def get(self, path: str, **kwargs):
            return client.get(path, **kwargs)

        def token(self, path: str = "/") -> str:
            html = client.get(path).get_data(as_text=True)
            found = re.search(r'name="csrf_token" value="([^"]+)"', html)
            assert found, "no CSRF field on the page"
            return found.group(1)

        def post(self, path: str, data: dict | None = None, **kwargs):
            payload = dict(data or {})
            payload.setdefault("csrf_token", self.token())
            kwargs.setdefault("follow_redirects", True)
            return client.post(path, data=payload, **kwargs)

    return Browser()
