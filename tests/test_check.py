"""FR-41: validating a whole data folder.

The point of check is that it keeps going. Every other load stops at the first
bad row so nothing overwrites it (FR-38); these tests break the data in several
ways at once and expect every problem back in one pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cubit.core import ERROR, WARNING, Storage, check_data

HEADER = "id,date,start,end,duration_minutes,project_id,category,note\n"


def codes(report) -> list[str]:
    return [problem.code for problem in report.problems]


def append(storage: Storage, year: int, month: int, *rows: str) -> None:
    path = storage.month_path(year, month)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(row + "\n")


def test_a_good_folder_is_clean(storage: Storage) -> None:
    report = check_data(storage)

    assert report.is_clean
    assert not report.has_errors
    assert (report.projects, report.entries, report.months) == (3, 6, 2)


def test_an_empty_folder_is_clean(empty_storage: Storage) -> None:
    report = check_data(empty_storage)
    assert report.is_clean
    assert (report.projects, report.entries, report.months) == (0, 0, 0)


def test_a_malformed_row_names_the_file_and_row(storage: Storage) -> None:
    append(storage, 2026, 9, "f00001,2026-09-22,,,notanumber,acme-web,,Broken")

    report = check_data(storage)
    problem = next(p for p in report.problems if p.code == "malformed-row")

    assert problem.level == ERROR
    assert problem.path == storage.month_path(2026, 9)
    assert problem.row == 6
    assert "whole number" in problem.message
    assert "row 6" in problem.where


def test_one_bad_file_does_not_hide_the_others(storage: Storage) -> None:
    """The whole reason check exists: report everything, not the first thing."""
    storage.month_path(2026, 10).write_text(HEADER + "zzz,2026-10-01,,,60,acme-web,,Bad\n")
    append(storage, 2026, 9, "f00001,2026-09-22,,,30,ghost,,Unknown project")

    report = check_data(storage)

    assert "malformed-row" in codes(report)
    assert "unknown-project" in codes(report)


def test_an_unknown_project_is_an_error(storage: Storage) -> None:
    """FR-40."""
    append(storage, 2026, 9, "f00001,2026-09-22,,,30,ghost-project,,Nowhere")

    problem = next(p for p in check_data(storage).problems if p.code == "unknown-project")
    assert problem.level == ERROR
    assert "ghost-project" in problem.message


def test_a_duplicate_id_in_one_file(storage: Storage) -> None:
    append(storage, 2026, 9, "a3f9c1,2026-09-22,,,30,acme-web,,Same id again")

    problem = next(p for p in check_data(storage).problems if p.code == "duplicate-id")
    assert problem.level == ERROR
    assert "more than once in this file" in problem.message


def test_a_duplicate_id_across_files(storage: Storage) -> None:
    """Ids are unique across every file, not just their own (REQUIREMENTS 4.1)."""
    append(storage, 2026, 8, "a3f9c1,2026-08-20,,,30,acme-web,,Same id in another month")

    problem = next(p for p in check_data(storage).problems if p.code == "duplicate-id")
    assert "2026-08.csv" in problem.message or "2026-09.csv" in problem.message


def test_an_entry_filed_in_the_wrong_month(storage: Storage) -> None:
    append(storage, 2026, 9, "f00001,2026-08-15,,,30,acme-web,,Wrong file")

    problem = next(p for p in check_data(storage).problems if p.code == "wrong-month")
    assert problem.level == ERROR
    assert "2026-08.csv" in problem.message


def test_times_that_disagree_with_the_duration_are_a_warning(storage: Storage) -> None:
    """FR-41: duration_minutes is the source of truth, so this changes no total."""
    append(storage, 2026, 9, "f00001,2026-09-22,09:00,10:00,90,acme-web,,Mismatch")

    problem = next(p for p in check_data(storage).problems if p.code == "duration-mismatch")
    assert problem.level == WARNING
    assert "60m" in problem.message and "90m" in problem.message


def test_a_timer_past_midnight_is_not_a_mismatch(storage: Storage) -> None:
    """FR-9: end before start means the next day, not a broken row."""
    assert "duration-mismatch" not in codes(check_data(storage))  # d90a11 is 23:40-00:25


def test_an_unregistered_category_is_a_warning(storage: Storage) -> None:
    """FR-44."""
    append(storage, 2026, 9, "f00001,2026-09-22,,,30,acme-web,invoicing,New category")

    problem = next(p for p in check_data(storage).problems if p.code == "unregistered-category")
    assert problem.level == WARNING
    assert "1 entry uses #invoicing on acme-web" in problem.message


def test_unregistered_categories_are_counted_not_repeated(storage: Storage) -> None:
    append(
        storage,
        2026,
        9,
        "f00001,2026-09-22,,,30,acme-web,invoicing,One",
        "f00002,2026-09-23,,,30,acme-web,invoicing,Two",
    )

    problems = [p for p in check_data(storage).problems if p.code == "unregistered-category"]
    assert len(problems) == 1
    assert "2 entries use #invoicing" in problems[0].message


def test_a_broken_projects_file_is_reported_once(storage: Storage) -> None:
    storage.projects_path.write_text("projects:\n  - id: Acme-Web\n    name: x\n", "utf-8")

    report = check_data(storage)
    assert "projects-invalid" in codes(report)
    # Without projects there is nothing to check entries against, and check says so.
    assert "projects-unreadable" in codes(report)


def test_a_broken_config_is_reported(storage: Storage) -> None:
    storage.config_path.write_text("theme: neon\n", "utf-8")
    assert "config-invalid" in codes(check_data(storage))


def test_a_timer_on_a_missing_project(storage: Storage) -> None:
    storage.timer_path.parent.mkdir(parents=True, exist_ok=True)
    storage.timer_path.write_text(
        '{"project_id": "ghost", "started_at": "2026-09-22T09:00:00+02:00"}', "utf-8"
    )

    problem = next(p for p in check_data(storage).problems if p.path == storage.timer_path)
    assert problem.level == ERROR
    assert "ghost" in problem.message


def test_a_timer_on_an_archived_project_is_a_warning(storage: Storage) -> None:
    storage.timer_path.parent.mkdir(parents=True, exist_ok=True)
    storage.timer_path.write_text(
        '{"project_id": "old-site", "started_at": "2026-09-22T09:00:00+02:00"}', "utf-8"
    )

    problem = next(p for p in check_data(storage).problems if p.code == "archived-timer")
    assert problem.level == WARNING


def test_a_broken_timer_file_is_reported(storage: Storage) -> None:
    storage.timer_path.parent.mkdir(parents=True, exist_ok=True)
    storage.timer_path.write_text("{not json", "utf-8")
    assert "timer-invalid" in codes(check_data(storage))


def test_problems_are_grouped_by_file(storage: Storage) -> None:
    """Fixing one file should mean reading one block, not hunting."""
    append(
        storage,
        2026,
        8,
        "f00001,2026-08-20,,,30,ghost,,Unknown",
        "f00002,2026-08-21,09:00,10:00,90,acme-web,,Mismatch",
    )
    append(storage, 2026, 9, "f00003,2026-09-22,,,30,ghost,,Unknown")

    paths = [str(p.path) for p in check_data(storage).problems if p.path]
    assert paths == sorted(paths)


def test_check_never_writes_anything(storage: Storage) -> None:
    """FR-38: reporting a problem must not change the file it is in."""
    append(storage, 2026, 9, "f00001,2026-09-22,,,30,ghost,,Unknown")
    before = {
        path: path.read_bytes() for path in sorted(storage.data_dir.rglob("*")) if path.is_file()
    }

    check_data(storage)

    after = {
        path: path.read_bytes() for path in sorted(storage.data_dir.rglob("*")) if path.is_file()
    }
    assert after == before


def test_problem_reads_as_a_sentence(storage: Storage) -> None:
    append(storage, 2026, 9, "f00001,2026-09-22,,,30,ghost,,Unknown")
    problem = next(p for p in check_data(storage).problems if p.code == "unknown-project")
    assert str(problem).startswith(str(storage.month_path(2026, 9)))


def test_errors_and_warnings_are_counted_apart(storage: Storage) -> None:
    append(
        storage,
        2026,
        9,
        "f00001,2026-09-22,,,30,ghost,,Unknown project",
        "f00002,2026-09-23,,,30,acme-web,invoicing,New category",
    )
    report = check_data(storage)

    assert len(report.errors) == 1
    assert len(report.warnings) == 1
    assert report.has_errors
    assert not report.is_clean


def test_a_folder_that_was_never_created(tmp_path: Path) -> None:
    report = check_data(Storage(tmp_path / "nothing-here"))
    assert report.is_clean  # nothing to complain about, and nothing to read


@pytest.mark.parametrize("level", [ERROR, WARNING])
def test_the_two_levels_are_the_documented_ones(level: str) -> None:
    assert level in {"error", "warning"}
