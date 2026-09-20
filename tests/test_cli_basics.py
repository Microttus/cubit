"""FR-24 to FR-26: the executable, its errors and where it looks for data."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cubit import __version__
from cubit.cli.exit_codes import EXIT_ERROR, EXIT_OK, EXIT_USAGE
from cubit.cli.main import app


def test_version(cli) -> None:
    result = cli("--version")
    assert result.exit_code == EXIT_OK
    assert result.stdout.strip() == f"cubit {__version__}"


def test_every_command_has_help(cli) -> None:
    """FR-24."""
    top = cli("--help")
    assert top.exit_code == EXIT_OK
    for name in ["init", "start", "stop", "status", "cancel", "add", "list", "edit", "rm"]:
        assert name in top.stdout
        assert cli(name, "--help").exit_code == EXIT_OK

    for name in ["add", "list", "show", "edit", "rate", "archive", "unarchive", "category"]:
        assert cli("project", name, "--help").exit_code == EXIT_OK


def test_help_does_not_leak_requirement_ids(cli) -> None:
    """--help is for users; FR-ids belong in the source."""
    assert "FR-" not in cli("--help").stdout
    assert "FR-" not in cli("add", "--help").stdout
    assert "FR-" not in cli("project", "--help").stdout


def test_init_creates_the_folder(cli_empty) -> None:
    result = cli_empty("init")
    assert result.exit_code == EXIT_OK

    data_dir: Path = cli_empty.data_dir
    assert (data_dir / "config.yaml").exists()
    assert (data_dir / "projects.yaml").exists()
    assert (data_dir / "entries").is_dir()
    assert "Created" in result.stdout


def test_init_twice_says_so(cli_empty) -> None:
    cli_empty("init")
    result = cli_empty("init")
    assert result.exit_code == EXIT_OK
    assert "already set up" in result.stdout


def test_a_command_before_init_explains_itself(cli_empty) -> None:
    """FR-25: short message, a hint, no traceback."""
    result = cli_empty("list")
    assert result.exit_code == EXIT_ERROR
    assert "No cubit data folder" in result.output
    assert "cubit init" in result.output
    assert "Traceback" not in result.output


def test_a_user_error_gives_a_message_a_hint_and_no_traceback(cli) -> None:
    """FR-25."""
    result = cli("add", "ghost", "1h", "--yes")
    assert result.exit_code == EXIT_ERROR
    assert "Error: Unknown project 'ghost'." in result.output
    assert "Hint:" in result.output
    assert "Traceback" not in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_a_bad_duration_is_a_user_error(cli) -> None:
    """FR-25 and FR-27."""
    result = cli("add", "acme-web", "bananas", "--yes")
    assert result.exit_code == EXIT_ERROR
    assert "Cannot read 'bananas' as a duration." in result.output
    assert "1h30m" in result.output


def test_a_missing_argument_is_a_usage_error(cli) -> None:
    assert cli("add").exit_code == EXIT_USAGE


def test_data_dir_option_beats_the_environment(sample_dir: Path, tmp_path: Path) -> None:
    """FR-26: --data-dir, then CUBIT_DATA_DIR, then the default."""
    elsewhere = tmp_path / "elsewhere"
    runner = CliRunner(env={"NO_COLOR": "1", "CUBIT_DATA_DIR": str(elsewhere)})

    result = runner.invoke(app, ["--data-dir", str(sample_dir), "project", "list"])
    assert result.exit_code == EXIT_OK
    assert "Acme website" in result.stdout


def test_the_environment_variable_is_used_when_no_option_is_given(sample_dir: Path) -> None:
    """FR-26."""
    runner = CliRunner(env={"NO_COLOR": "1", "CUBIT_DATA_DIR": str(sample_dir)})
    result = runner.invoke(app, ["project", "list"])
    assert result.exit_code == EXIT_OK
    assert "Acme website" in result.stdout


def test_output_has_no_escape_codes_when_not_a_terminal(cli) -> None:
    """FR-59: colour is for terminals, and NO_COLOR always wins."""
    result = cli("project", "list")
    assert "\x1b[" not in result.stdout
