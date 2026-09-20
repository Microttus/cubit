"""FR-11 to FR-16 and FR-44 from the command line."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from cubit.cli.exit_codes import EXIT_ERROR, EXIT_OK
from cubit.core import ProjectStatus, Storage


def test_project_add(cli, storage: Storage) -> None:
    """FR-11."""
    result = cli(
        "project",
        "add",
        "beta-app",
        "--name",
        "Beta app",
        "--client",
        "Beta AS",
        "--rate",
        "110.50",
        "--rate-from",
        "2026-09-01",
        "--budget",
        "40",
        "-c",
        "software-coding",
    )
    assert result.exit_code == EXIT_OK

    project = storage.get_project("beta-app")
    assert project.name == "Beta app"
    assert project.client == "Beta AS"
    assert project.budget_hours == Decimal("40")
    assert project.rates[0].rate == Decimal("110.50")
    assert project.categories == ["software-coding"]


def test_project_add_refuses_a_taken_id(cli) -> None:
    """FR-12."""
    result = cli("project", "add", "acme-web", "--name", "Clash")
    assert result.exit_code == EXIT_ERROR
    assert "already exists" in result.output


def test_project_add_refuses_a_bad_id(cli) -> None:
    """FR-12: the id is a lowercase slug."""
    result = cli("project", "add", "Acme Web", "--name", "Acme")
    assert result.exit_code == EXIT_ERROR


def test_project_add_rejects_a_bad_rate(cli) -> None:
    result = cli("project", "add", "beta-app", "--name", "Beta", "--rate", "free")
    assert result.exit_code == EXIT_ERROR
    assert "as an amount" in result.output


def test_project_list_hides_archived_until_asked(cli) -> None:
    """FR-13."""
    plain = cli("project", "list").stdout
    assert "acme-web" in plain
    assert "old-site" not in plain

    everything = cli("project", "list", "--all").stdout
    assert "old-site" in everything
    assert "archived" in everything


def test_project_list_shows_rate_budget_and_logged_time(cli) -> None:
    """FR-28: readable columns with the numbers that matter."""
    lines = cli("project", "list").stdout.splitlines()
    assert lines[0].split() == ["ID", "NAME", "CLIENT", "STATUS", "RATE", "BUDGET", "LOGGED"]

    acme = next(line for line in lines if line.startswith("acme-web"))
    assert "105" in acme  # the rate valid today
    assert "120" in acme  # the budget
    assert "4h25m" in acme  # 90 + 90 + 40 + 45 minutes, August included


def test_project_list_by_client(cli) -> None:
    result = cli("project", "list", "--client", "IceCube Solutions")
    assert "internal" in result.stdout
    assert "acme-web" not in result.stdout


def test_project_show(cli) -> None:
    """FR-11, FR-14."""
    result = cli("project", "show", "acme-web")
    assert result.exit_code == EXIT_OK
    assert "Acme website" in result.stdout
    assert "from 2026-01-01  95" in result.stdout
    assert "from 2026-07-01  105" in result.stdout
    assert "#software-coding" in result.stdout
    assert "120 h" in result.stdout


def test_project_show_says_when_a_project_is_unrated(cli) -> None:
    """FR-15."""
    assert "unrated" in cli("project", "show", "internal").stdout


def test_project_show_unknown(cli) -> None:
    result = cli("project", "show", "ghost")
    assert result.exit_code == EXIT_ERROR
    assert "Unknown project" in result.output


def test_project_edit(cli, storage: Storage) -> None:
    """FR-11."""
    assert cli("project", "edit", "acme-web", "-n", "Acme site").exit_code == EXIT_OK
    assert storage.get_project("acme-web").name == "Acme site"

    assert cli("project", "edit", "acme-web", "--no-budget").exit_code == EXIT_OK
    assert storage.get_project("acme-web").budget_hours is None


def test_project_edit_cannot_change_the_id(cli) -> None:
    """FR-12: there is no option for it."""
    assert "--id" not in cli("project", "edit", "--help").stdout


def test_project_rate_adds_a_step(cli, storage: Storage) -> None:
    """FR-14."""
    result = cli("project", "rate", "acme-web", "120", "--from", "2027-01-01")
    assert result.exit_code == EXIT_OK
    assert "2027-01-01" in result.stdout

    rates = storage.get_project("acme-web").rates
    assert [step.valid_from for step in rates][-1] == date(2027, 1, 1)
    assert rates[-1].rate == Decimal("120")


def test_project_archive_and_unarchive(cli, storage: Storage) -> None:
    """FR-13."""
    assert cli("project", "archive", "internal").exit_code == EXIT_OK
    assert storage.get_project("internal").status is ProjectStatus.ARCHIVED
    assert storage.load_entries(project_id="internal")  # entries stay

    assert cli("project", "unarchive", "internal").exit_code == EXIT_OK
    assert storage.get_project("internal").status is ProjectStatus.ACTIVE


def test_project_rm_needs_an_empty_project(cli, storage: Storage) -> None:
    """FR-16."""
    refused = cli("project", "rm", "acme-web", "--yes")
    assert refused.exit_code == EXIT_ERROR
    assert "archive" in refused.output.lower()
    assert storage.get_project("acme-web")

    cli("project", "add", "beta-app", "--name", "Beta app")
    assert cli("project", "rm", "beta-app", "--yes").exit_code == EXIT_OK
    assert "beta-app" not in {p.id for p in storage.load_projects()}


def test_project_rm_asks_first(cli, storage: Storage) -> None:
    cli("project", "add", "beta-app", "--name", "Beta app")
    declined = cli("project", "rm", "beta-app", input="n\n")
    assert declined.exit_code != EXIT_OK
    assert storage.get_project("beta-app")


def test_project_category_add_and_list(cli, storage: Storage) -> None:
    """FR-44, FR-46."""
    assert cli("project", "category", "add", "internal", "Code Review").exit_code == EXIT_OK
    assert "code-review" in storage.get_project("internal").categories

    listed = cli("project", "category", "list", "acme-web").stdout.split()
    # Most recently used first: software-coding was logged on the 19th.
    assert listed[0] == "#software-coding"
    assert "#testing" in listed  # registered but never used, so last


def test_project_category_rm_only_unregisters(cli, storage: Storage) -> None:
    """FR-55: entries keep the category they already have."""
    result = cli("project", "category", "rm", "acme-web", "testing")
    assert result.exit_code == EXIT_OK
    assert "testing" not in storage.get_project("acme-web").categories

    assert cli("project", "category", "rm", "acme-web", "invoicing").exit_code == EXIT_ERROR


def test_projects_yaml_keeps_its_comments_through_the_cli(cli, storage: Storage) -> None:
    """The whole point of round-tripping: hand-written notes survive."""
    cli("project", "edit", "acme-web", "-n", "Acme site")
    cli("project", "rate", "acme-web", "120")
    cli("project", "category", "add", "acme-web", "invoicing")

    text = storage.projects_path.read_text(encoding="utf-8")
    assert "# registered sub-categories, shown as #name" in text
    assert "# raised after the summer" in text
    assert "# kept for history only" in text
