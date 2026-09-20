"""FR-37 to FR-42: reading, writing and validating the monthly entry files."""

from __future__ import annotations

from datetime import date, time
from pathlib import Path

import pytest

from cubit.core import DataFileError, Entry, Storage
from cubit.core.storage import ENTRY_COLUMNS


def _entry(entry_id: str, day: date, **kwargs) -> Entry:
    fields = {
        "id": entry_id,
        "date": day,
        "duration_minutes": 60,
        "project_id": "acme-web",
        **kwargs,
    }
    return Entry(**fields)


def test_columns_are_the_documented_ones() -> None:
    """AGENT.md: columns may not be renamed or reordered without a migration note."""
    assert ENTRY_COLUMNS == (
        "id",
        "date",
        "start",
        "end",
        "duration_minutes",
        "project_id",
        "category",
        "note",
    )


def test_load_month_reads_hand_written_rows(storage: Storage) -> None:
    entries = {entry.id: entry for entry in storage.load_month(2026, 9)}
    assert list(entries) == ["b71c02", "a3f9c1", "c48d7e", "d90a11"]

    timed = entries["a3f9c1"]
    assert timed.date == date(2026, 9, 18)
    assert timed.start == time(9, 5)
    assert timed.end == time(10, 35)
    assert timed.duration_minutes == 90
    assert timed.category == "software-coding"

    manual = entries["b71c02"]
    assert manual.start is None and manual.end is None
    assert manual.category is None  # blank means uncategorized


def test_load_month_keeps_commas_inside_a_quoted_note(storage: Storage) -> None:
    note = next(e for e in storage.load_month(2026, 9) if e.id == "c48d7e").note
    assert note == "Sprint planning call, with Acme"


def test_load_month_of_a_missing_file_is_empty(storage: Storage) -> None:
    assert storage.load_month(2030, 1) == []


def test_months_lists_only_real_entry_files(storage: Storage) -> None:
    (storage.entries_dir / "notes.txt").write_text("ignored", encoding="utf-8")
    (storage.entries_dir / "backup.csv").write_text("ignored", encoding="utf-8")
    assert storage.months() == [(2026, 8), (2026, 9)]


def test_load_entries_spans_months_in_stable_order(storage: Storage) -> None:
    """FR-42: date, then start, then id."""
    entries = storage.load_all_entries()
    assert [entry.id for entry in entries] == [
        "4d5e6f",  # 2026-08-31, no start time, so it sorts before 08:00
        "9a1b2c",
        "b71c02",  # 2026-09-18, no start time
        "a3f9c1",
        "c48d7e",
        "d90a11",
    ]


def test_load_entries_filters_by_date_range(storage: Storage) -> None:
    """Month/year boundaries: 31 August and 1 September are different files."""
    august = storage.load_entries(date(2026, 8, 1), date(2026, 8, 31))
    assert {entry.id for entry in august} == {"9a1b2c", "4d5e6f"}

    boundary = storage.load_entries(date(2026, 8, 31), date(2026, 9, 18))
    assert {entry.id for entry in boundary} == {"9a1b2c", "4d5e6f", "a3f9c1", "b71c02"}

    single_day = storage.load_entries(date(2026, 9, 19), date(2026, 9, 19))
    assert {entry.id for entry in single_day} == {"c48d7e", "d90a11"}


def test_load_entries_filters_by_project_and_category(storage: Storage) -> None:
    """FR-6 and FR-49."""
    assert {e.id for e in storage.load_entries(project_id="internal")} == {"4d5e6f", "b71c02"}
    assert {e.id for e in storage.load_entries(category="software-coding")} == {
        "9a1b2c",
        "a3f9c1",
        "d90a11",
    }


def test_load_entries_only_opens_the_months_it_needs(storage: Storage, monkeypatch) -> None:
    """Performance: a range must not read the whole history."""
    opened: list[tuple[int, int]] = []
    original = Storage.load_month

    def spy(self: Storage, year: int, month: int) -> list[Entry]:
        opened.append((year, month))
        return original(self, year, month)

    monkeypatch.setattr(Storage, "load_month", spy)
    storage.load_entries(date(2026, 9, 1), date(2026, 9, 30))
    assert opened == [(2026, 9)]


def test_add_entry_writes_to_the_month_of_its_date(storage: Storage) -> None:
    storage.add_entry(_entry("111111", date(2026, 10, 1)))
    assert storage.month_path(2026, 10).exists()
    assert [e.id for e in storage.load_month(2026, 10)] == ["111111"]


def test_add_entry_keeps_the_file_sorted(storage: Storage) -> None:
    storage.add_entry(_entry("000001", date(2026, 9, 17), start=time(8, 0), end=time(9, 0)))
    rows = storage.month_path(2026, 9).read_text(encoding="utf-8").splitlines()
    assert rows[1].startswith("000001,2026-09-17")


def test_add_entry_refuses_a_duplicate_id(storage: Storage) -> None:
    with pytest.raises(DataFileError, match="already used"):
        storage.add_entry(_entry("a3f9c1", date(2026, 9, 20)))


def test_update_entry_in_place(storage: Storage) -> None:
    """FR-7."""
    entry = storage.find_entry("b71c02")
    assert entry is not None
    storage.update_entry(entry.model_copy(update={"duration_minutes": 75, "note": "Fixed"}))

    updated = storage.find_entry("b71c02")
    assert updated is not None
    assert updated.duration_minutes == 75
    assert updated.note == "Fixed"
    assert len(storage.load_month(2026, 9)) == 4


def test_update_entry_moves_it_between_months(storage: Storage) -> None:
    entry = storage.find_entry("a3f9c1")
    assert entry is not None
    storage.update_entry(entry.model_copy(update={"date": date(2026, 8, 20)}))

    assert "a3f9c1" not in {e.id for e in storage.load_month(2026, 9)}
    assert "a3f9c1" in {e.id for e in storage.load_month(2026, 8)}


def test_update_entry_of_an_unknown_id_names_the_folder(storage: Storage) -> None:
    with pytest.raises(DataFileError, match="no entry with id"):
        storage.update_entry(_entry("ffffff", date(2026, 9, 20)))


def test_delete_entry(storage: Storage) -> None:
    deleted = storage.delete_entry("c48d7e")
    assert deleted.id == "c48d7e"
    assert storage.find_entry("c48d7e") is None

    with pytest.raises(DataFileError, match="no entry with id"):
        storage.delete_entry("c48d7e")


def test_deleting_the_last_entry_removes_the_month_file(storage: Storage) -> None:
    for entry_id in ["9a1b2c", "4d5e6f"]:
        storage.delete_entry(entry_id)
    assert not storage.month_path(2026, 8).exists()


def test_new_entry_id_is_six_hex_and_unused(storage: Storage) -> None:
    fresh = storage.new_entry_id()
    assert len(fresh) == 6
    assert int(fresh, 16) >= 0
    assert fresh not in storage.all_entry_ids()


def test_round_trip_keeps_the_file_byte_identical(storage: Storage) -> None:
    """Rewriting untouched data must not churn the file (FR-42)."""
    path = storage.month_path(2026, 9)
    before = path.read_text(encoding="utf-8")
    storage.save_month(2026, 9, storage.load_month(2026, 9))
    assert path.read_text(encoding="utf-8") == before


def test_a_note_with_a_comma_is_quoted_on_write(storage: Storage) -> None:
    storage.add_entry(_entry("000002", date(2026, 9, 21), note='Call, then "notes"'))
    reloaded = storage.find_entry("000002")
    assert reloaded is not None
    assert reloaded.note == 'Call, then "notes"'


def test_a_bad_header_names_the_file_and_row(storage: Storage) -> None:
    """FR-38."""
    path = storage.month_path(2026, 9)
    path.write_text("id,date,minutes\n", encoding="utf-8")
    with pytest.raises(DataFileError) as caught:
        storage.load_month(2026, 9)
    assert str(path) in str(caught.value)
    assert "row 1" in str(caught.value)


@pytest.mark.parametrize(
    ("row", "message"),
    [
        ("zzzzzz,2026-09-20,,,60,acme-web,,Note", "six hex"),
        ("111111,20-09-2026,,,60,acme-web,,Note", "YYYY-MM-DD"),
        ("111111,2026-09-20,9am,10am,60,acme-web,,Note", "HH:MM"),
        ("111111,2026-09-20,,,sixty,acme-web,,Note", "whole number"),
        ("111111,2026-09-20,,,0,acme-web,,Note", "duration_minutes"),
        ("111111,2026-09-20,09:00,,60,acme-web,,Note", "both"),
        ("111111,2026-09-20,,,60,acme-web,,Note,extra", "expected 8 columns"),
        ("111111,2026-09-20,,,60,Acme-Web,,Note", "slug"),
    ],
)
def test_a_bad_row_names_the_file_and_row(storage: Storage, row: str, message: str) -> None:
    path = storage.month_path(2026, 9)
    path.write_text(f"{','.join(ENTRY_COLUMNS)}\n{row}\n", encoding="utf-8")

    with pytest.raises(DataFileError) as caught:
        storage.load_month(2026, 9)

    assert str(path) in str(caught.value)
    assert "row 2" in str(caught.value)
    assert message in str(caught.value)


def test_a_bad_row_is_never_overwritten(storage: Storage) -> None:
    """FR-38: invalid data is never overwritten or dropped."""
    path = storage.month_path(2026, 9)
    broken = f"{','.join(ENTRY_COLUMNS)}\n111111,2026-09-20,,,zero,acme-web,,Note\n"
    path.write_text(broken, encoding="utf-8")

    with pytest.raises(DataFileError):
        storage.add_entry(_entry("222222", date(2026, 9, 21)))

    assert path.read_text(encoding="utf-8") == broken


def test_blank_lines_and_a_byte_order_mark_are_tolerated(storage: Storage) -> None:
    """Hand-edited files, and files saved by a spreadsheet, still load."""
    path = storage.month_path(2026, 9)
    path.write_text(
        "﻿" + ",".join(ENTRY_COLUMNS) + "\n\n111111,2026-09-20,,,60,acme-web,,Note\n\n",
        encoding="utf-8",
    )
    assert [entry.id for entry in storage.load_month(2026, 9)] == ["111111"]


def test_an_empty_file_is_no_entries(storage: Storage) -> None:
    storage.month_path(2026, 9).write_text("", encoding="utf-8")
    assert storage.load_month(2026, 9) == []


def test_writes_leave_no_temporary_files_behind(storage: Storage) -> None:
    storage.add_entry(_entry("111111", date(2026, 9, 22)))
    leftovers = [path.name for path in storage.entries_dir.iterdir() if path.suffix == ".tmp"]
    assert leftovers == []


def test_storage_over_an_uninitialised_folder_reads_as_empty(tmp_path: Path) -> None:
    store = Storage(tmp_path / "nothing-here")
    assert store.load_all_entries() == []
    assert store.load_projects() == []
    assert store.read_timer() is None
    assert not store.exists
