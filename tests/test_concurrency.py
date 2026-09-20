"""FR-39: the CLI and the web app may write at the same time.

Writes go through a temporary file plus os.replace while the folder is held
under a lock, so a reader never sees half a file and no write is lost.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
import threading
from datetime import date
from pathlib import Path

from cubit.core import Entry, Storage

WRITER = """
import sys
from datetime import date

from cubit.core import Entry, Storage

data_dir, prefix, count = sys.argv[1], sys.argv[2], int(sys.argv[3])
store = Storage(data_dir)
for index in range(count):
    store.add_entry(
        Entry(
            id=f"{prefix}{index:04d}",
            date=date(2026, 9, 20),
            duration_minutes=30,
            project_id="acme-web",
            note=f"from {prefix}",
        )
    )
"""


def _run_writer(data_dir: Path, prefix: str, count: int) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-c", textwrap.dedent(WRITER), str(data_dir), prefix, str(count)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_two_processes_writing_at_once_lose_nothing(sample_dir: Path) -> None:
    """A real second process, because that is what 'cubit web' is."""
    per_writer = 8
    processes = [_run_writer(sample_dir, prefix, per_writer) for prefix in ("aa", "bb")]
    for process in processes:
        _, stderr = process.communicate(timeout=60)
        assert process.returncode == 0, stderr

    store = Storage(sample_dir)
    written = [entry for entry in store.load_month(2026, 9) if entry.date == date(2026, 9, 20)]
    assert len(written) == 2 * per_writer
    assert len({entry.id for entry in written}) == 2 * per_writer


def test_threads_writing_at_once_lose_nothing(sample_dir: Path) -> None:
    per_thread = 10
    barrier = threading.Barrier(3)
    failures: list[BaseException] = []

    def write(prefix: str) -> None:
        store = Storage(sample_dir)  # each "interface" has its own Storage
        barrier.wait()
        try:
            for index in range(per_thread):
                store.add_entry(
                    Entry(
                        id=f"{prefix}{index:04d}",
                        date=date(2026, 9, 20),
                        duration_minutes=30,
                        project_id="acme-web",
                    )
                )
        except BaseException as error:  # noqa: BLE001 - reported below
            failures.append(error)

    threads = [threading.Thread(target=write, args=(prefix,)) for prefix in ("cc", "dd")]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=60)

    assert not failures
    store = Storage(sample_dir)
    written = [entry for entry in store.load_month(2026, 9) if entry.date == date(2026, 9, 20)]
    assert len(written) == 2 * per_thread


def test_a_reader_never_sees_a_half_written_file(sample_dir: Path) -> None:
    """os.replace is atomic, so every read gets a complete file."""
    store = Storage(sample_dir)
    stop = threading.Event()
    problems: list[BaseException] = []

    def read_forever() -> None:
        while not stop.is_set():
            try:
                store.load_month(2026, 9)
            except BaseException as error:  # noqa: BLE001 - reported below
                problems.append(error)
                return

    reader = threading.Thread(target=read_forever)
    reader.start()
    try:
        writer = Storage(sample_dir)
        for index in range(40):
            writer.add_entry(
                Entry(
                    id=f"ee{index:04d}",
                    date=date(2026, 9, 20),
                    duration_minutes=30,
                    project_id="acme-web",
                )
            )
    finally:
        stop.set()
        reader.join(timeout=30)

    assert not problems


def test_the_lock_file_stays_out_of_the_data(empty_storage: Storage) -> None:
    with empty_storage.lock():
        pass
    assert empty_storage.lock_path.parent.name == ".state"
    assert not list(empty_storage.entries_dir.glob("*.lock"))
