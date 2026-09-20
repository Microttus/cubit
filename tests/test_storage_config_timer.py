"""config.yaml, the timer state file and where the data folder comes from."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cubit.core import Config, CubitError, DataFileError, Storage, TimerState
from cubit.core.storage import DATA_DIR_ENV_VAR, DEFAULT_DATA_DIR, resolve_data_dir

UTC_PLUS_2 = timezone(timedelta(hours=2))


def test_resolve_data_dir_prefers_the_explicit_folder(tmp_path: Path) -> None:
    """FR-26: --data-dir, then CUBIT_DATA_DIR, then the default."""
    env = {DATA_DIR_ENV_VAR: str(tmp_path / "from-env")}
    assert resolve_data_dir(tmp_path / "explicit", env) == tmp_path / "explicit"


def test_resolve_data_dir_falls_back_to_the_environment(tmp_path: Path) -> None:
    env = {DATA_DIR_ENV_VAR: str(tmp_path / "from-env")}
    assert resolve_data_dir(None, env) == tmp_path / "from-env"


def test_resolve_data_dir_falls_back_to_the_default() -> None:
    assert resolve_data_dir(None, {}) == DEFAULT_DATA_DIR
    assert Path.home() / "cubit-data" == DEFAULT_DATA_DIR


def test_resolve_data_dir_expands_a_tilde() -> None:
    assert resolve_data_dir("~/elsewhere", {}) == Path.home() / "elsewhere"


def test_init_creates_the_documented_layout(tmp_path: Path) -> None:
    store = Storage(tmp_path / "data")
    assert store.init() is True

    assert store.config_path.exists()
    assert store.projects_path.exists()
    assert store.entries_dir.is_dir()
    assert store.state_dir.is_dir()
    assert not store.timer_path.exists()  # only while a timer runs
    assert store.load_config() == Config()
    assert store.load_projects() == []


def test_init_is_safe_to_run_twice(tmp_path: Path) -> None:
    store = Storage(tmp_path / "data")
    store.init()
    store.save_config(Config(currency="NOK"))

    assert store.init() is False
    assert store.load_config().currency == "NOK"


def test_load_config_of_a_missing_file_is_the_defaults(tmp_path: Path) -> None:
    assert Storage(tmp_path / "nothing").load_config() == Config()


def test_save_config_keeps_comments(storage: Storage) -> None:
    storage.save_config(storage.load_config().model_copy(update={"currency": "NOK"}))

    text = storage.projects_path.parent.joinpath("config.yaml").read_text(encoding="utf-8")
    assert "# Cubit configuration. Edit by hand; comments are kept." in text
    assert "currency: NOK" in text
    assert storage.load_config().currency == "NOK"


def test_an_invalid_config_names_the_file(storage: Storage) -> None:
    """FR-38."""
    storage.config_path.write_text("theme: neon\n", encoding="utf-8")
    with pytest.raises(DataFileError) as caught:
        storage.load_config()
    assert str(storage.config_path) in str(caught.value)
    assert "theme" in str(caught.value)


def test_a_config_that_is_not_a_mapping_is_refused(storage: Storage) -> None:
    storage.config_path.write_text("- one\n- two\n", encoding="utf-8")
    with pytest.raises(DataFileError, match="mapping"):
        storage.load_config()


def test_no_timer_file_means_no_timer(empty_storage: Storage) -> None:
    assert empty_storage.read_timer() is None


def test_timer_round_trips_through_the_state_file(empty_storage: Storage) -> None:
    """FR-8: the CLI and the web app share one timer."""
    state = TimerState(
        project_id="acme-web",
        started_at=datetime(2026, 9, 18, 9, 5, 12, tzinfo=UTC_PLUS_2),
        category="software-coding",
        note="Landing page layout",
    )
    empty_storage.write_timer(state)

    # A second Storage stands in for the other interface.
    other = Storage(empty_storage.data_dir)
    assert other.read_timer() == state

    other.clear_timer()
    assert empty_storage.read_timer() is None


def test_the_timer_file_keeps_its_offset(empty_storage: Storage) -> None:
    """REQUIREMENTS 4.4: started_at is timezone-aware on disk too."""
    empty_storage.write_timer(
        TimerState(
            project_id="acme-web",
            started_at=datetime(2026, 9, 18, 9, 5, 12, tzinfo=UTC_PLUS_2),
        )
    )
    text = empty_storage.timer_path.read_text(encoding="utf-8")
    assert "2026-09-18T09:05:12+02:00" in text


def test_the_timer_file_lives_outside_the_synced_data(empty_storage: Storage) -> None:
    """REQUIREMENTS 4.4: kept out of entries/ and projects.yaml."""
    assert empty_storage.timer_path.parent.name == ".state"


def test_clearing_a_timer_that_is_not_running_is_fine(empty_storage: Storage) -> None:
    empty_storage.clear_timer()
    assert empty_storage.read_timer() is None


def test_broken_timer_json_names_the_file_and_line(empty_storage: Storage) -> None:
    empty_storage.timer_path.write_text("{not json", encoding="utf-8")
    with pytest.raises(DataFileError) as caught:
        empty_storage.read_timer()
    assert str(empty_storage.timer_path) in str(caught.value)
    assert caught.value.hint


def test_a_naive_timer_timestamp_is_refused(empty_storage: Storage) -> None:
    empty_storage.timer_path.write_text(
        '{"project_id": "acme-web", "started_at": "2026-09-18T09:05:12"}', encoding="utf-8"
    )
    with pytest.raises(DataFileError, match="UTC offset"):
        empty_storage.read_timer()


def test_menubar_title_is_a_setting(storage: Storage) -> None:
    """REQUIREMENTS 4.3: none | time | project-time, default time (FR-64)."""
    assert storage.load_config().menubar_title == "time"

    storage.config_path.write_text("menubar_title: project-time\n", encoding="utf-8")
    assert storage.load_config().menubar_title == "project-time"


def test_an_unknown_menubar_title_is_refused(storage: Storage) -> None:
    storage.config_path.write_text("menubar_title: flashing\n", encoding="utf-8")
    with pytest.raises(DataFileError, match="menubar_title"):
        storage.load_config()


def test_a_config_written_to_the_documented_shape_loads(storage: Storage) -> None:
    """Every key REQUIREMENTS 4.3 shows must be accepted, not just tolerated."""
    storage.config_path.write_text(
        "currency: NOK\n"
        "week_starts_on: monday\n"
        "budget_warning_percent: 80\n"
        "prompt_for_category: true\n"
        "theme: dark\n"
        "menubar_title: time\n",
        encoding="utf-8",
    )
    config = storage.load_config()
    assert (config.currency, config.theme, config.menubar_title) == ("NOK", "dark", "time")


def test_a_write_that_waits_too_long_is_an_ordinary_error(tmp_path: Path) -> None:
    """A menu bar app must not freeze on a lock another process is holding."""
    store = Storage(tmp_path / "data")
    store.init()
    blocker = Storage(tmp_path / "data")
    impatient = Storage(tmp_path / "data", lock_timeout=0.1)

    with blocker.lock(), pytest.raises(CubitError) as caught, impatient.lock():
        pass

    assert "busy" in caught.value.message
    assert caught.value.hint


def test_the_lock_is_released_after_a_failure(tmp_path: Path) -> None:
    store = Storage(tmp_path / "data")
    store.init()

    with pytest.raises(ValueError), store.lock():
        raise ValueError("boom")

    with store.lock():  # still acquirable
        pass
