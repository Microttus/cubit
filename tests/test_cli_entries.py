"""FR-1 to FR-7 and FR-27 from the command line."""

from __future__ import annotations

from datetime import date

import pytest

from cubit.cli.exit_codes import EXIT_ERROR, EXIT_OK
from cubit.core import Storage


def _entry_id(output: str) -> str:
    """The id cubit prints in square brackets after logging."""
    return output.rsplit("[", 1)[1].split("]", 1)[0]


def _table(output: str) -> tuple[str, list[str]]:
    """The heading line and the rows above the blank line before the totals."""
    lines = output.splitlines()
    rows: list[str] = []
    for line in lines[1:]:
        if not line.strip():
            break
        rows.append(line)
    return lines[0], rows


def test_add_logs_an_entry(cli, storage: Storage) -> None:
    """FR-5."""
    result = cli(
        "add",
        "acme-web",
        "1h30m",
        "-c",
        "software-coding",
        "--date",
        "2026-09-21",
        "-m",
        "Landing page",
        "--yes",
    )
    assert result.exit_code == EXIT_OK
    assert "1h30m" in result.stdout

    entry = storage.find_entry(_entry_id(result.stdout))
    assert entry is not None
    assert entry.date == date(2026, 9, 21)
    assert entry.duration_minutes == 90
    assert entry.category == "software-coding"
    assert entry.note == "Landing page"


@pytest.mark.parametrize("duration", ["90m", "1h30m", "1.5h", "1:30"])
def test_add_accepts_every_documented_duration(cli, storage: Storage, duration: str) -> None:
    """FR-27."""
    result = cli("add", "acme-web", duration, "--date", "2026-09-21", "--yes")
    assert result.exit_code == EXIT_OK

    entry = storage.find_entry(_entry_id(result.stdout))
    assert entry is not None
    assert entry.duration_minutes == 90


def test_add_with_a_start_time_fills_in_the_end(cli, storage: Storage) -> None:
    result = cli("add", "acme-web", "1h", "--date", "2026-09-21", "--start", "13:00", "--yes")
    entry = storage.find_entry(_entry_id(result.stdout))
    assert entry is not None
    assert (entry.start.isoformat(), entry.end.isoformat()) == ("13:00:00", "14:00:00")


def test_add_accepts_a_quoted_hash_category(cli, storage: Storage) -> None:
    """FR-51: -c is documented without the #, but a quoted one works."""
    result = cli("add", "internal", "30m", "-c", "#Ad Hoc", "--date", "2026-09-21", "--yes")
    entry = storage.find_entry(_entry_id(result.stdout))
    assert entry is not None
    assert entry.category == "ad-hoc"
    assert "ad-hoc" in storage.get_project("internal").categories


def test_add_to_an_archived_project_is_refused_then_forced(cli, storage: Storage) -> None:
    """FR-10."""
    refused = cli("add", "old-site", "1h", "--date", "2026-09-21", "--yes")
    assert refused.exit_code == EXIT_ERROR
    assert "archived" in refused.output

    forced = cli("add", "old-site", "1h", "--date", "2026-09-21", "--force", "--yes")
    assert forced.exit_code == EXIT_OK


def test_start_status_and_stop(cli, storage: Storage) -> None:
    """FR-1, FR-2, FR-3."""
    started = cli("start", "acme-web", "-c", "testing", "-m", "Unit tests", "--yes")
    assert started.exit_code == EXIT_OK
    assert "acme-web" in started.stdout
    assert "#testing" in started.stdout

    status = cli("status")
    assert status.exit_code == EXIT_OK
    assert "acme-web" in status.stdout
    assert "#testing" in status.stdout
    assert "Unit tests" in status.stdout

    stopped = cli("stop", "-m", "Wrote the tests")
    assert stopped.exit_code == EXIT_OK

    entry = storage.find_entry(_entry_id(stopped.stdout))
    assert entry is not None
    assert entry.note == "Wrote the tests"
    assert entry.category == "testing"
    assert storage.read_timer() is None


def test_status_without_a_timer(cli) -> None:
    result = cli("status")
    assert result.exit_code == EXIT_OK
    assert "No timer running." in result.stdout


def test_a_second_start_is_refused(cli) -> None:
    """FR-1."""
    cli("start", "acme-web", "--yes")
    result = cli("start", "internal", "--yes")
    assert result.exit_code == EXIT_ERROR
    assert "already running" in result.output


def test_stop_without_a_timer_is_an_error(cli) -> None:
    result = cli("stop")
    assert result.exit_code == EXIT_ERROR
    assert "No timer is running." in result.output


def test_cancel_drops_the_timer_without_logging(cli, storage: Storage) -> None:
    """FR-4."""
    before = len(storage.load_all_entries())
    cli("start", "acme-web", "--yes")

    result = cli("cancel")
    assert result.exit_code == EXIT_OK
    assert "Nothing was logged" in result.stdout
    assert storage.read_timer() is None
    assert len(storage.load_all_entries()) == before


def test_list_defaults_to_this_month(cli, storage: Storage) -> None:
    """A default that reads one file rather than the whole history."""
    today = date.today()
    cli("add", "acme-web", "1h", "--date", today.isoformat(), "--yes")

    result = cli("list")
    assert result.exit_code == EXIT_OK
    assert today.isoformat() in result.stdout
    assert "2026-09-18" not in result.stdout or today.strftime("%Y-%m") == "2026-09"


def test_list_all_shows_every_entry_with_a_total(cli) -> None:
    """FR-6 and FR-28."""
    result = cli("list", "--all")
    assert result.exit_code == EXIT_OK
    for entry_id in ["4d5e6f", "9a1b2c", "b71c02", "a3f9c1", "c48d7e", "d90a11"]:
        assert entry_id in result.stdout
    # 30 + 90 + 45 + 90 + 40 + 45 minutes
    assert "6 entries" in result.stdout
    assert "5h40m (5.67 h)" in result.stdout


def test_list_columns_line_up(cli) -> None:
    """FR-28: aligned columns."""
    header, rows = _table(cli("list", "--all").stdout)

    assert header.startswith("ID")
    assert len(rows) == 6
    for row in rows:
        assert row.index("2026-") == header.index("DATE")


def test_list_filters(cli) -> None:
    """FR-6."""
    by_project = cli("list", "--all", "--project", "internal").stdout
    assert "4d5e6f" in by_project and "a3f9c1" not in by_project

    by_client = cli("list", "--all", "--client", "Acme Corp").stdout
    assert "a3f9c1" in by_client and "4d5e6f" not in by_client

    by_category = cli("list", "--all", "-c", "project-management").stdout
    assert "c48d7e" in by_category and "a3f9c1" not in by_category

    by_range = cli("list", "--from", "2026-08-01", "--to", "2026-08-31").stdout
    assert "9a1b2c" in by_range and "a3f9c1" not in by_range


def test_list_limit_and_empty_result(cli) -> None:
    _, rows = _table(cli("list", "--all", "--limit", "2").stdout)
    assert len(rows) == 2

    empty = cli("list", "--from", "2020-01-01", "--to", "2020-12-31")
    assert empty.exit_code == EXIT_OK
    assert "No entries found." in empty.stdout


def test_list_accepts_today_and_yesterday(cli) -> None:
    assert cli("list", "--from", "yesterday", "--to", "today").exit_code == EXIT_OK


def test_list_rejects_a_bad_date(cli) -> None:
    result = cli("list", "--from", "last tuesday")
    assert result.exit_code == EXIT_ERROR
    assert "YYYY-MM-DD" in result.output


def test_edit_changes_one_field(cli, storage: Storage) -> None:
    """FR-7."""
    result = cli("edit", "b71c02", "-d", "1h", "-m", "Invoicing, September")
    assert result.exit_code == EXIT_OK

    entry = storage.find_entry("b71c02")
    assert entry is not None
    assert entry.duration_minutes == 60
    assert entry.note == "Invoicing, September"
    assert entry.category is None  # untouched


def test_edit_can_clear_the_category_and_the_times(cli, storage: Storage) -> None:
    cli("edit", "a3f9c1", "--no-category", "--no-times")
    entry = storage.find_entry("a3f9c1")
    assert entry is not None
    assert entry.category is None
    assert entry.start is None and entry.end is None


def test_edit_refuses_contradictory_options(cli) -> None:
    assert cli("edit", "a3f9c1", "-c", "testing", "--no-category").exit_code != EXIT_OK
    assert cli("edit", "a3f9c1", "--start", "09:00", "--no-times").exit_code != EXIT_OK


def test_edit_an_unknown_entry(cli) -> None:
    result = cli("edit", "ffffff", "-m", "nope")
    assert result.exit_code == EXIT_ERROR
    assert "No entry with id" in result.output


def test_rm_asks_first_and_can_be_declined(cli, storage: Storage) -> None:
    """FR-7."""
    declined = cli("rm", "c48d7e", input="n\n")
    assert declined.exit_code != EXIT_OK
    assert storage.find_entry("c48d7e") is not None

    confirmed = cli("rm", "c48d7e", input="y\n")
    assert confirmed.exit_code == EXIT_OK
    assert storage.find_entry("c48d7e") is None


def test_rm_with_yes_does_not_ask(cli, storage: Storage) -> None:
    result = cli("rm", "c48d7e", "--yes")
    assert result.exit_code == EXIT_OK
    assert "Delete this entry?" not in result.stdout
    assert storage.find_entry("c48d7e") is None
