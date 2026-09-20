"""The report commands end to end, against the sample data folder."""

from __future__ import annotations

from datetime import date

from cubit.cli.exit_codes import EXIT_ERROR, EXIT_OK
from cubit.core import Storage


def _row(output: str, label: str) -> list[str]:
    """The cells of the table row starting with ``label``."""
    line = next(line for line in output.splitlines() if line.startswith(label))
    return line[len(label) :].split()


def test_report_week(cli) -> None:
    """FR-17: total, by project and by day."""
    result = cli("report", "week", "2026-09-18")
    assert result.exit_code == EXIT_OK

    assert "Week 38, 2026  2026-09-14 to 2026-09-20" in result.stdout
    assert "3h40m (3.67 h)" in result.stdout
    assert "PROJECT" in result.stdout and "DAY" in result.stdout

    assert _row(result.stdout, "Acme website")[:2] == ["2h55m", "2.92"]
    assert _row(result.stdout, "2026-09-18")[:2] == ["2h15m", "2.25"]
    assert _row(result.stdout, "2026-09-16")[:2] == ["0m", "0.00"]  # a quiet day


def test_report_week_accepts_the_ways_of_naming_one(cli) -> None:
    assert cli("report", "week", "2026-W38").exit_code == EXIT_OK
    assert cli("report", "week", "this").exit_code == EXIT_OK
    assert cli("report", "week", "last").exit_code == EXIT_OK
    assert cli("report", "week").exit_code == EXIT_OK


def test_report_month(cli) -> None:
    """FR-18: by project, client and week."""
    result = cli("report", "month", "2026-09")
    assert result.exit_code == EXIT_OK

    assert "September 2026  2026-09-01 to 2026-09-30" in result.stdout
    for section in ["PROJECT", "CLIENT", "WEEK", "CATEGORY"]:
        assert section in result.stdout

    assert _row(result.stdout, "Acme Corp")[:2] == ["2h55m", "2.92"]
    assert _row(result.stdout, "2026-W38")[:2] == ["3h40m", "3.67"]
    assert _row(result.stdout, "2026-W40")[:2] == ["0m", "0.00"]


def test_report_month_totals_categories_across_projects(cli) -> None:
    """FR-60."""
    result = cli("report", "month", "2026-09")
    assert _row(result.stdout, "#software-coding")[:2] == ["2h15m", "2.25"]
    assert _row(result.stdout, "uncategorized")[:2] == ["45m", "0.75"]


def test_report_by_category_breaks_each_project_down(cli) -> None:
    """FR-54."""
    plain = cli("report", "month", "2026-09").stdout
    detailed = cli("report", "month", "2026-09", "--by-category").stdout

    assert detailed.count("CATEGORY") > plain.count("CATEGORY")
    assert "Internal work" in detailed


def test_reports_show_unrated_time_in_its_own_column(cli) -> None:
    """FR-15 and FR-28: money still lines up."""
    result = cli("report", "month", "2026-09")
    assert "UNRATED" in result.stdout
    assert _row(result.stdout, "Internal work")[-2:] == ["-", "45m"]
    assert _row(result.stdout, "Acme website")[-2:] == ["306.25", "-"]


def test_report_project(cli) -> None:
    """FR-19, FR-49."""
    result = cli("report", "project", "acme-web")
    assert result.exit_code == EXIT_OK

    assert "total     4h25m (4.42 h)" in result.stdout
    assert "earned    463.75 EUR" in result.stdout
    assert "budget    4h25m of 120h (3.7%), 115h35m left" in result.stdout
    assert _row(result.stdout, "#software-coding")[:2] == ["3h45m", "3.75"]


def test_report_project_with_a_period(cli) -> None:
    """FR-21."""
    result = cli("report", "project", "acme-web", "--from", "2026-09-01", "--to", "2026-09-30")
    assert "total     4h25m" in result.stdout  # the whole history
    assert "period    2h55m" in result.stdout  # only September


def test_report_project_can_list_its_entries(cli) -> None:
    """FR-19: the entry list."""
    result = cli("report", "project", "acme-web", "--entries")
    for entry_id in ["9a1b2c", "a3f9c1", "c48d7e", "d90a11"]:
        assert entry_id in result.stdout


def test_report_project_says_when_there_is_no_budget(cli) -> None:
    assert "budget    none set" in cli("report", "project", "internal").stdout


def test_report_project_warns_near_the_budget(cli, storage: Storage) -> None:
    """FR-22: at the threshold, and once exceeded."""
    cli("project", "edit", "acme-web", "--budget", "5")
    assert "88.3%" in cli("report", "project", "acme-web").stdout

    cli("project", "edit", "acme-web", "--budget", "4")
    over = cli("report", "project", "acme-web").stdout
    assert "over budget" in over
    assert "25m over budget" in over


def test_report_project_unknown(cli) -> None:
    result = cli("report", "project", "ghost")
    assert result.exit_code == EXIT_ERROR
    assert "Unknown project" in result.output


def test_report_client(cli) -> None:
    """FR-20."""
    result = cli("report", "client", "Acme Corp")
    assert result.exit_code == EXIT_OK

    assert "4h25m (4.42 h)" in result.stdout
    assert "463.75 EUR" in result.stdout
    assert "2 projects" in result.stdout  # acme-web and the archived old-site
    assert _row(result.stdout, "Acme website")[:2] == ["4h25m", "4.42"]


def test_report_client_is_case_insensitive(cli) -> None:
    assert cli("report", "client", "acme corp").exit_code == EXIT_OK


def test_report_client_unknown(cli) -> None:
    result = cli("report", "client", "Nobody")
    assert result.exit_code == EXIT_ERROR
    assert "No projects for client" in result.output


def test_report_category(cli) -> None:
    """FR-61."""
    result = cli("report", "category", "software-coding")
    assert result.exit_code == EXIT_OK

    assert "#software-coding" in result.stdout
    assert "3h45m (3.75 h)" in result.stdout
    assert _row(result.stdout, "Acme website")[:2] == ["3h45m", "3.75"]


def test_report_category_accepts_a_quoted_hash(cli) -> None:
    """FR-51."""
    assert "3h45m" in cli("report", "category", "#Software Coding").stdout


def test_report_category_with_nothing_logged(cli) -> None:
    result = cli("report", "category", "invoicing")
    assert result.exit_code == EXIT_OK
    assert "Nothing logged to that category." in result.stdout


def test_reports_take_a_category_filter(cli) -> None:
    """FR-21."""
    result = cli("report", "month", "2026-09", "-c", "software-coding")
    assert "filtered to #software-coding" in result.stdout
    assert "2h15m (2.25 h)" in result.stdout
    assert "Internal work" not in result.stdout


def test_reports_take_a_custom_range(cli) -> None:
    """FR-21."""
    result = cli("report", "month", "--from", "2026-08-01", "--to", "2026-09-30")
    assert "Custom range  2026-08-01 to 2026-09-30" in result.stdout
    assert "5h40m (5.67 h)" in result.stdout


def test_a_half_open_range_is_refused(cli) -> None:
    result = cli("report", "week", "--from", "2026-08-01")
    assert result.exit_code == EXIT_ERROR
    assert "needs both ends" in result.output


def test_a_backwards_range_is_refused(cli) -> None:
    result = cli("report", "month", "--from", "2026-09-30", "--to", "2026-09-01")
    assert result.exit_code == EXIT_ERROR
    assert "is after" in result.output


def test_an_unreadable_period_is_a_user_error(cli) -> None:
    result = cli("report", "week", "bananas")
    assert result.exit_code == EXIT_ERROR
    assert "2026-W39" in result.output
    assert "Traceback" not in result.output


def test_the_week_start_follows_the_config(cli, storage: Storage) -> None:
    """config.yaml may ask for Sunday weeks."""
    config = storage.load_config()
    storage.save_config(config.model_copy(update={"week_starts_on": "sunday"}))

    result = cli("report", "week", "2026-09-18")
    assert "2026-09-13 to 2026-09-19" in result.stdout


def test_the_currency_follows_the_config(cli, storage: Storage) -> None:
    config = storage.load_config()
    storage.save_config(config.model_copy(update={"currency": "NOK"}))

    result = cli("report", "project", "acme-web")
    assert "463.75 NOK" in result.stdout


def test_a_report_of_an_empty_period(cli) -> None:
    result = cli("report", "month", "2020-01")
    assert result.exit_code == EXIT_OK
    assert "0m (0.00 h)" in result.stdout


def test_every_report_has_help(cli) -> None:
    """FR-24."""
    assert cli("report", "--help").exit_code == EXIT_OK
    for name in ["week", "month", "project", "client", "category"]:
        result = cli("report", name, "--help")
        assert result.exit_code == EXIT_OK
        assert "FR-" not in result.stdout


def test_reports_default_to_the_current_period(cli, storage: Storage) -> None:
    """'this' is the default, so a bare command is about now."""
    today = date.today()
    cli("add", "acme-web", "1h", "--date", today.isoformat(), "--yes")

    week = cli("report", "week").stdout
    month = cli("report", "month").stdout
    assert "1h" in week
    assert today.strftime("%B %Y") in month


def test_a_period_does_not_shrink_the_project_total_or_its_budget(cli) -> None:
    """FR-19: the period narrows the hours shown, not the history or the budget."""
    narrow = cli("report", "project", "acme-web", "--from", "2026-09-19", "--to", "2026-09-19")

    assert "total     4h25m (4.42 h)" in narrow.stdout  # every hour ever logged
    assert "period    1h25m (1.42 h)" in narrow.stdout  # only the 19th
    assert "budget    4h25m of 120h" in narrow.stdout  # measured against the total


def test_a_period_does_not_shrink_the_client_report(cli) -> None:
    """FR-20 with FR-21."""
    narrow = cli("report", "client", "Acme Corp", "--from", "2026-09-19", "--to", "2026-09-19")
    assert "1h25m (1.42 h)" in narrow.stdout
    assert "2 projects" in narrow.stdout


def test_a_period_narrows_the_category_report(cli) -> None:
    """FR-61 with FR-21."""
    assert "3h45m" in cli("report", "category", "software-coding").stdout
    narrow = cli(
        "report", "category", "software-coding", "--from", "2026-09-01", "--to", "2026-09-30"
    )
    assert "2h15m (2.25 h)" in narrow.stdout
