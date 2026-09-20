"""The milestone 5 commands: check, export and completion (FR-41, FR-23, FR-29)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from cubit.cli.completion import (
    COMPLETE_VAR,
    SHELLS,
    complete_any_project,
    complete_category,
    complete_client,
    complete_format,
    complete_project,
    complete_shell,
    completion_script,
)
from cubit.cli.exit_codes import EXIT_ERROR, EXIT_OK
from cubit.core import Storage


def append(storage: Storage, year: int, month: int, row: str) -> None:
    with storage.month_path(year, month).open("a", encoding="utf-8") as handle:
        handle.write(row + "\n")


# ------------------------------------------------------------------- check


def test_check_of_a_good_folder(cli) -> None:
    """FR-41."""
    result = cli("check")
    assert result.exit_code == EXIT_OK
    assert "Everything checks out." in result.stdout
    assert "3 projects and 6 entries" in result.stdout


def test_check_reports_problems_and_exits_non_zero(cli, storage: Storage) -> None:
    append(storage, 2026, 9, "f00001,2026-09-22,,,30,ghost-project,,Nowhere")

    result = cli("check")
    assert result.exit_code == EXIT_ERROR
    assert "ghost-project" in result.output
    assert "1 error, 0 warnings." in result.output
    assert "Traceback" not in result.output


def test_check_writes_paths_relative_to_the_data_folder(cli, storage: Storage) -> None:
    """An absolute path per line is unreadable when the folder is nested deep."""
    append(storage, 2026, 9, "f00001,2026-09-22,,,30,ghost-project,,Nowhere")

    output = cli("check").output
    assert "entries/2026-09.csv" in output
    assert str(storage.data_dir) not in output


def test_warnings_alone_do_not_fail(cli, storage: Storage) -> None:
    """A category worth registering is not a reason for a script to stop."""
    append(storage, 2026, 9, "f00001,2026-09-22,,,30,acme-web,invoicing,New category")

    result = cli("check")
    assert result.exit_code == EXIT_OK
    assert "0 errors, 1 warning." in result.output


def test_strict_fails_on_warnings_too(cli, storage: Storage) -> None:
    append(storage, 2026, 9, "f00001,2026-09-22,,,30,acme-web,invoicing,New category")
    assert cli("check", "--strict").exit_code == EXIT_ERROR


def test_check_before_init(cli_empty) -> None:
    result = cli_empty("check")
    assert result.exit_code == EXIT_ERROR
    assert "cubit init" in result.output


def test_check_labels_each_problem(cli, storage: Storage) -> None:
    append(storage, 2026, 9, "f00001,2026-09-22,,,30,ghost,,Unknown")
    append(storage, 2026, 9, "f00002,2026-09-23,,,30,acme-web,invoicing,New category")

    output = cli("check").output
    assert "error  " in output
    assert "warning  " in output


# ------------------------------------------------------------------ export


@pytest.mark.parametrize(
    ("command", "args"),
    [
        ("week", ["2026-09-18"]),
        ("month", ["2026-09"]),
        ("project", ["acme-web"]),
        ("client", ["Acme Corp"]),
        ("category", ["software-coding"]),
    ],
)
def test_every_report_exports_in_both_formats(cli, command: str, args: list[str]) -> None:
    """FR-23."""
    markdown = cli("report", command, *args, "--format", "markdown")
    assert markdown.exit_code == EXIT_OK
    assert markdown.stdout.startswith("# ")
    assert "|---|" in markdown.stdout

    csv_out = cli("report", command, *args, "--format", "csv")
    assert csv_out.exit_code == EXIT_OK
    assert "Time,Hours" in csv_out.stdout


def test_export_writes_to_a_file(cli, tmp_path: Path) -> None:
    target = tmp_path / "reports" / "september.md"
    result = cli("report", "month", "2026-09", "--format", "markdown", "-o", str(target))

    assert result.exit_code == EXIT_OK
    assert f"Wrote {target}" in result.stdout
    text = target.read_text(encoding="utf-8")
    assert text.startswith("# September 2026")
    assert "Acme website" in text


def test_export_matches_what_the_table_shows(cli) -> None:
    table = cli("report", "month", "2026-09").stdout
    exported = cli("report", "month", "2026-09", "--format", "markdown").stdout

    assert "3h40m" in table and "3h40m" in exported
    assert "306.25" in table and "306.25" in exported


def test_export_respects_the_filters(cli) -> None:
    """FR-21 applies to an export as much as to the table."""
    text = cli("report", "month", "2026-09", "-c", "software-coding", "--format", "markdown")
    assert "Acme website" in text.stdout
    assert "Internal work" not in text.stdout


def test_the_default_format_is_still_the_table(cli) -> None:
    assert not cli("report", "week", "2026-09-18").stdout.startswith("# ")


def test_an_unknown_format_is_a_user_error(cli) -> None:
    result = cli("report", "week", "2026-09-18", "--format", "pdf")
    assert result.exit_code == EXIT_ERROR
    assert "text, csv, markdown" in result.output


def test_a_project_export_carries_the_budget(cli) -> None:
    """FR-19, FR-22."""
    text = cli("report", "project", "acme-web", "--format", "markdown").stdout
    assert "| Budget | 4h25m of 120h" in text
    assert "| Remaining | 115h35m |" in text


def test_an_export_shows_what_the_report_shows(cli) -> None:
    """--entries controls the entry list in both the table and the export."""
    without = cli("report", "project", "acme-web", "--format", "markdown").stdout
    with_them = cli("report", "project", "acme-web", "--entries", "--format", "markdown").stdout

    assert "## Entries" not in without
    assert "## Entries" in with_them
    assert "Landing page layout" in with_them


# -------------------------------------------------------------- completion


def test_completion_offers_active_projects(cli, sample_dir: Path, monkeypatch) -> None:
    """FR-29."""
    monkeypatch.setenv("CUBIT_DATA_DIR", str(sample_dir))

    assert complete_project("") == ["acme-web", "internal"]
    assert complete_project("a") == ["acme-web"]
    assert "old-site" not in complete_project("")  # archived


def test_completion_of_project_management_commands_includes_archived(
    sample_dir: Path, monkeypatch
) -> None:
    monkeypatch.setenv("CUBIT_DATA_DIR", str(sample_dir))
    assert "old-site" in complete_any_project("")


def test_completion_offers_categories_and_clients(sample_dir: Path, monkeypatch) -> None:
    monkeypatch.setenv("CUBIT_DATA_DIR", str(sample_dir))

    assert "software-coding" in complete_category("")
    assert complete_category("soft") == ["software-coding"]
    assert "Acme Corp" in complete_client("")
    assert complete_client("ice") == ["IceCube Solutions"]


def test_completion_offers_the_formats_and_shells() -> None:
    assert complete_format("") == ["text", "csv", "markdown"]
    assert complete_format("c") == ["csv"]
    assert complete_shell("z") == ["zsh"]


def test_completion_is_silent_when_there_is_no_data_folder(tmp_path, monkeypatch) -> None:
    """A callback runs mid-keystroke: it must never raise into the prompt."""
    monkeypatch.setenv("CUBIT_DATA_DIR", str(tmp_path / "nothing-here"))

    assert complete_project("") == []
    assert complete_category("") == []
    assert complete_client("") == []


def test_completion_survives_a_broken_projects_file(sample_dir: Path, monkeypatch) -> None:
    monkeypatch.setenv("CUBIT_DATA_DIR", str(sample_dir))
    (sample_dir / "projects.yaml").write_text("projects: [[[", encoding="utf-8")

    assert complete_project("") == []
    assert complete_category("") == []


@pytest.mark.parametrize("shell", SHELLS)
def test_a_completion_script_is_written_for_every_shell(cli, shell: str) -> None:
    result = cli("completion", shell)
    assert result.exit_code == EXIT_OK
    assert "cubit" in result.stdout
    assert COMPLETE_VAR in result.stdout


def test_an_unknown_shell_is_a_user_error(cli) -> None:
    result = cli("completion", "tcsh")
    assert result.exit_code == EXIT_ERROR
    assert "bash, zsh, fish" in result.output


def test_the_script_speaks_the_protocol_cubit_answers(sample_dir: Path) -> None:
    """The script and the handler have to agree, or completion fails silently.

    Click and Typer disagree about the shape of the callback instruction, so
    this takes the instruction straight out of the generated script and asks
    cubit to complete with it, end to end.
    """
    executable = Path(sys.executable).parent / "cubit"
    if not executable.exists():  # pragma: no cover - only when not installed
        pytest.skip("the cubit console script is not installed")

    script = completion_script("zsh")
    instruction = script.split(f"{COMPLETE_VAR}=")[1].split()[0]

    env = {
        **os.environ,
        "CUBIT_DATA_DIR": str(sample_dir),
        COMPLETE_VAR: instruction,
        "_TYPER_COMPLETE_ARGS": "cubit add ",
    }
    result = subprocess.run([str(executable)], capture_output=True, text=True, env=env, check=False)

    assert "acme-web" in result.stdout, result.stdout + result.stderr
    assert "not supported" not in result.stdout + result.stderr


def test_the_completion_command_needs_no_data_folder(cli_empty) -> None:
    """You install completion before you have anything to complete."""
    assert cli_empty("completion", "zsh").exit_code == EXIT_OK
