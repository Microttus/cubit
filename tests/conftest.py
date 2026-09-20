"""Shared fixtures. Tests never touch a real data folder: they copy the sample
folder in ``tests/fixtures/`` into ``tmp_path`` (AGENT.md)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cubit.core import Storage

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_DATA = FIXTURES / "sample-data"


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
