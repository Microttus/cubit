"""FR-82: syncing the data folder between computers through a git remote."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cubit.cli.exit_codes import EXIT_ERROR, EXIT_OK
from cubit.cli.main import app
from cubit.core import CubitError, Storage, run_sync, setup_sync

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    "NO_COLOR": "1",
}


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for key, value in GIT_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))


@pytest.fixture
def remote(tmp_path: Path) -> str:
    path = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "--initial-branch", "main", str(path)], check=True)
    return str(path)


@pytest.fixture
def laptop(tmp_path: Path, remote: str) -> Storage:
    """The computer that already has data, synced for the first time."""
    store = Storage(tmp_path / "laptop")
    store.init()
    setup_sync(store, remote)
    return store


def _log(store: Storage, text: str) -> None:
    month = store.entries_dir / "2026-10.csv"
    previous = month.read_text(encoding="utf-8") if month.exists() else ""
    store._write_atomic(month, previous + text)


def test_setup_ignores_state_and_pushes(laptop: Storage, remote: str) -> None:
    assert (laptop.data_dir / ".gitignore").read_text(encoding="utf-8") == ".state/\n.DS_Store\n"
    tracked = subprocess.run(
        ["git", "-C", str(laptop.data_dir), "ls-files"], capture_output=True, text=True
    ).stdout.split()
    assert "projects.yaml" in tracked
    assert not any(name.startswith(".state") for name in tracked)
    heads = subprocess.run(
        ["git", "-C", remote, "branch", "--list"], capture_output=True, text=True
    ).stdout
    assert "main" in heads


def test_setup_twice_is_harmless(laptop: Storage, remote: str) -> None:
    again = setup_sync(laptop, remote)
    assert not again.initialised and not again.cloned


def test_setup_refuses_a_different_remote(laptop: Storage, tmp_path: Path) -> None:
    with pytest.raises(CubitError, match="already syncs"):
        setup_sync(laptop, str(tmp_path / "other.git"))


def test_setup_without_folder_or_remote_explains(tmp_path: Path) -> None:
    with pytest.raises(CubitError, match="No cubit data folder"):
        setup_sync(Storage(tmp_path / "nothing"))


def test_a_new_computer_clones_the_data(laptop: Storage, remote: str, tmp_path: Path) -> None:
    _log(laptop, "x\n")
    run_sync(laptop)

    desktop = Storage(tmp_path / "desktop")
    report = setup_sync(desktop, remote)

    assert report.cloned
    assert (desktop.entries_dir / "2026-10.csv").read_text(encoding="utf-8").endswith("x\n")
    assert desktop.exists


def test_changes_travel_both_ways(laptop: Storage, remote: str, tmp_path: Path) -> None:
    desktop = Storage(tmp_path / "desktop")
    setup_sync(desktop, remote)

    _log(laptop, "from-laptop\n")
    assert run_sync(laptop).pushed

    report = run_sync(desktop)
    assert report.pulled == 1
    assert "from-laptop" in (desktop.entries_dir / "2026-10.csv").read_text(encoding="utf-8")


def test_sync_with_nothing_to_do(laptop: Storage) -> None:
    report = run_sync(laptop)
    assert (report.committed, report.pulled, report.pushed) == (False, 0, False)


def test_unrelated_edits_on_both_computers_merge(
    laptop: Storage, remote: str, tmp_path: Path
) -> None:
    desktop = Storage(tmp_path / "desktop")
    setup_sync(desktop, remote)

    _log(laptop, "a\n")
    run_sync(laptop)
    desktop.projects_path.write_text(
        desktop.projects_path.read_text(encoding="utf-8") + "# note\n", encoding="utf-8"
    )
    report = run_sync(desktop)

    assert report.committed and report.pulled == 1 and report.pushed
    assert "# note" in desktop.projects_path.read_text(encoding="utf-8")
    assert (desktop.entries_dir / "2026-10.csv").exists()


def test_a_real_conflict_is_reported_and_leaves_the_folder_clean(
    laptop: Storage, remote: str, tmp_path: Path
) -> None:
    desktop = Storage(tmp_path / "desktop")
    setup_sync(desktop, remote)

    _log(laptop, "laptop\n")
    run_sync(laptop)
    _log(desktop, "desktop\n")

    with pytest.raises(CubitError, match="could not merge") as raised:
        run_sync(desktop)
    assert "Nothing was lost" in (raised.value.hint or "")

    status = subprocess.run(
        ["git", "-C", str(desktop.data_dir), "status", "--porcelain"],
        capture_output=True,
        text=True,
    ).stdout
    assert status == ""
    assert "desktop" in (desktop.entries_dir / "2026-10.csv").read_text(encoding="utf-8")


def test_a_running_timer_blocks_sync(laptop: Storage) -> None:
    from cubit.core import start_timer

    laptop.entries_dir.mkdir(exist_ok=True)
    laptop.projects_path.write_text(
        "projects:\n  - id: p\n    name: P\n    client: C\n    status: active\n",
        encoding="utf-8",
    )
    start_timer(laptop, "p")
    with pytest.raises(CubitError, match="timer"):
        run_sync(laptop)


def test_the_timer_is_never_committed(laptop: Storage) -> None:
    laptop.state_dir.mkdir(exist_ok=True)
    (laptop.state_dir / "secret_key").write_text("k\n", encoding="utf-8")
    assert not run_sync(laptop).committed


def test_sync_before_setup_explains(empty_storage: Storage) -> None:
    with pytest.raises(CubitError, match="not set up") as raised:
        run_sync(empty_storage)
    assert "cubit sync setup" in (raised.value.hint or "")


def test_cli_setup_then_sync(tmp_path: Path, remote: str) -> None:
    runner = CliRunner(env=GIT_ENV)
    data = str(tmp_path / "cli-data")

    assert runner.invoke(app, ["--data-dir", data, "init"]).exit_code == EXIT_OK
    setup = runner.invoke(app, ["--data-dir", data, "sync", "setup", remote])
    assert setup.exit_code == EXIT_OK, setup.output
    assert "Uploaded" in setup.stdout

    again = runner.invoke(app, ["--data-dir", data, "sync"])
    assert again.exit_code == EXIT_OK, again.output
    assert "Already in sync" in again.stdout


def test_cli_sync_without_setup_fails_politely(cli_empty) -> None:
    cli_empty("init")
    result = cli_empty("sync")
    assert result.exit_code == EXIT_ERROR
    assert "cubit sync setup" in result.output


def test_a_starter_folder_adopts_the_remote_instead_of_clashing(
    laptop: Storage, remote: str, tmp_path: Path
) -> None:
    """The app creates an empty data folder on first launch; setup must not push it."""
    _log(laptop, "real\n")
    run_sync(laptop)

    desktop = Storage(tmp_path / "desktop")
    desktop.init()
    report = setup_sync(desktop, remote)

    assert report.cloned
    assert "real" in (desktop.entries_dir / "2026-10.csv").read_text(encoding="utf-8")
    assert run_sync(desktop).pulled == 0


def test_two_folders_with_data_are_not_merged_blindly(
    laptop: Storage, remote: str, tmp_path: Path
) -> None:
    desktop = Storage(tmp_path / "desktop")
    desktop.init()
    _log(desktop, "mine\n")

    with pytest.raises(CubitError, match="already holds cubit data") as raised:
        setup_sync(desktop, remote)
    assert "Move this folder aside" in (raised.value.hint or "")
    assert "mine" in (desktop.entries_dir / "2026-10.csv").read_text(encoding="utf-8")


def test_an_unfinished_rebase_blocks_sync(laptop: Storage, remote: str, tmp_path: Path) -> None:
    (laptop.data_dir / ".git" / "rebase-merge").mkdir()
    with pytest.raises(CubitError, match="never finished"):
        run_sync(laptop)


def test_a_tracked_ds_store_is_dropped(laptop: Storage) -> None:
    (laptop.data_dir / ".DS_Store").write_bytes(b"x")
    subprocess.run(["git", "-C", str(laptop.data_dir), "add", "--force", ".DS_Store"], check=True)
    subprocess.run(["git", "-C", str(laptop.data_dir), "commit", "-qm", "oops"], check=True)

    assert run_sync(laptop).committed
    tracked = subprocess.run(
        ["git", "-C", str(laptop.data_dir), "ls-files"], capture_output=True, text=True
    ).stdout.split()
    assert ".DS_Store" not in tracked
