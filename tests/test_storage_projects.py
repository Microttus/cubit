"""FR-11 to FR-15, FR-44 and FR-45: projects.yaml, comments and all."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from cubit.core import DataFileError, Project, ProjectError, ProjectStatus, Rate, Storage


def test_load_projects_reads_the_sample_folder(storage: Storage) -> None:
    projects = storage.load_projects()
    assert [project.id for project in projects] == ["acme-web", "internal", "old-site"]

    acme = projects[0]
    assert acme.name == "Acme website"
    assert acme.client == "Acme Corp"
    assert acme.status is ProjectStatus.ACTIVE
    assert acme.categories == ["software-coding", "project-management", "testing"]
    assert acme.budget_hours == Decimal("120")
    assert [rate.rate for rate in acme.rates] == [Decimal("95"), Decimal("105")]

    assert projects[1].rates == []  # unrated by design
    assert projects[2].status is ProjectStatus.ARCHIVED


def test_get_project_by_id(storage: Storage) -> None:
    assert storage.get_project("internal").name == "Internal work"


def test_get_unknown_project_gives_a_message_and_a_hint(storage: Storage) -> None:
    """FR-25: short message plus hint, no traceback for the user."""
    with pytest.raises(ProjectError) as caught:
        storage.get_project("nope")
    assert "nope" in caught.value.message
    assert caught.value.hint


def test_saving_keeps_the_comments_in_the_file(storage: Storage) -> None:
    """The point of ruamel: a hand-written file survives a rewrite."""
    project = storage.get_project("acme-web")
    storage.update_project(project.model_copy(update={"name": "Acme website v2"}))

    text = storage.projects_path.read_text(encoding="utf-8")
    assert "# Cubit projects. Edit by hand; comments are kept." in text
    assert "# registered sub-categories, shown as #name" in text
    assert "# raised after the summer" in text
    assert "# kept for history only" in text
    assert "name: Acme website v2" in text


def test_saving_keeps_the_order_of_the_projects(storage: Storage) -> None:
    storage.update_project(storage.get_project("internal").model_copy(update={"client": "Us"}))
    assert [p.id for p in storage.load_projects()] == ["acme-web", "internal", "old-site"]


def test_add_project_appends_and_round_trips(storage: Storage) -> None:
    """FR-11."""
    new = Project(
        id="beta-app",
        name="Beta app",
        client="Beta AS",
        budget_hours=Decimal("40"),
        categories=["#Software Coding"],
        rates=[Rate(valid_from=date(2026, 9, 1), rate=Decimal("110.50"))],
    )
    storage.add_project(new)

    reloaded = storage.get_project("beta-app")
    assert reloaded.name == "Beta app"
    assert reloaded.categories == ["software-coding"]
    assert reloaded.rates[0].rate == Decimal("110.50")
    assert "110.50" in storage.projects_path.read_text(encoding="utf-8")


def test_add_project_refuses_an_id_that_is_taken(storage: Storage) -> None:
    """FR-12: the id is unique."""
    with pytest.raises(ProjectError, match="already exists"):
        storage.add_project(Project(id="acme-web", name="Something else"))


def test_update_project_refuses_an_unknown_id(storage: Storage) -> None:
    with pytest.raises(ProjectError, match="Unknown project"):
        storage.update_project(Project(id="ghost", name="Ghost"))


def test_archiving_keeps_the_project_and_its_entries(storage: Storage) -> None:
    """FR-13."""
    project = storage.get_project("internal")
    storage.update_project(project.model_copy(update={"status": ProjectStatus.ARCHIVED}))

    assert storage.get_project("internal").status is ProjectStatus.ARCHIVED
    assert {e.id for e in storage.load_entries(project_id="internal")} == {"4d5e6f", "b71c02"}


def test_clearing_the_budget_removes_the_key(storage: Storage) -> None:
    project = storage.get_project("acme-web")
    storage.update_project(project.model_copy(update={"budget_hours": None}))

    assert storage.get_project("acme-web").budget_hours is None
    assert "budget_hours" not in storage.projects_path.read_text(encoding="utf-8")


def test_register_category_appends_to_the_project(storage: Storage) -> None:
    """FR-45: using a new category registers it on the project."""
    updated = storage.register_category("acme-web", "#Code Review")
    assert updated.categories == [
        "software-coding",
        "project-management",
        "testing",
        "code-review",
    ]
    assert storage.get_project("acme-web").categories[-1] == "code-review"


def test_register_category_is_a_no_op_when_already_registered(storage: Storage) -> None:
    before = storage.projects_path.read_text(encoding="utf-8")
    storage.register_category("acme-web", "Software Coding")
    assert storage.projects_path.read_text(encoding="utf-8") == before


def test_register_category_is_per_project(storage: Storage) -> None:
    """FR-47: the same name in two projects is registered separately."""
    storage.register_category("internal", "software-coding")
    assert storage.get_project("internal").categories == ["admin", "software-coding"]
    assert storage.get_project("acme-web").categories == [
        "software-coding",
        "project-management",
        "testing",
    ]


def test_register_category_on_an_unknown_project(storage: Storage) -> None:
    with pytest.raises(ProjectError):
        storage.register_category("ghost", "admin")


def test_broken_yaml_names_the_file_and_line(storage: Storage) -> None:
    """FR-38."""
    storage.projects_path.write_text("projects:\n  - id: acme\n   name: bad\n", encoding="utf-8")
    with pytest.raises(DataFileError) as caught:
        storage.load_projects()
    assert str(storage.projects_path) in str(caught.value)
    assert "line" in str(caught.value)


def test_an_invalid_project_names_the_file_and_the_project(storage: Storage) -> None:
    storage.projects_path.write_text(
        "projects:\n  - id: Acme-Web\n    name: Acme website\n", encoding="utf-8"
    )
    with pytest.raises(DataFileError) as caught:
        storage.load_projects()
    assert "Acme-Web" in str(caught.value)
    assert "slug" in str(caught.value)


def test_a_duplicate_project_id_is_refused(storage: Storage) -> None:
    storage.projects_path.write_text(
        "projects:\n  - id: acme-web\n    name: One\n  - id: acme-web\n    name: Two\n",
        encoding="utf-8",
    )
    with pytest.raises(DataFileError, match="used twice"):
        storage.load_projects()


def test_invalid_projects_are_never_overwritten(storage: Storage) -> None:
    """FR-38: a failed load must not cost the user their file."""
    broken = "projects:\n  - id: acme-web\n    name: Acme\n    budget_hours: -5\n"
    storage.projects_path.write_text(broken, encoding="utf-8")

    with pytest.raises(DataFileError):
        storage.register_category("acme-web", "admin")

    assert storage.projects_path.read_text(encoding="utf-8") == broken


def test_an_empty_projects_file_is_no_projects(storage: Storage) -> None:
    storage.projects_path.write_text("", encoding="utf-8")
    assert storage.load_projects() == []


def test_a_new_project_is_written_in_the_documented_key_order(empty_storage: Storage) -> None:
    """REQUIREMENTS 4.2 shows id, name, client, status, categories, budget_hours, rates."""
    empty_storage.add_project(
        Project(
            id="beta-app",
            name="Beta app",
            client="Beta AS",
            categories=["admin"],
            budget_hours=Decimal("40"),
            rates=[Rate(valid_from=date(2026, 9, 1), rate=Decimal("110"))],
        )
    )
    keys = [
        line.split(":")[0].strip("- ")
        for line in empty_storage.projects_path.read_text(encoding="utf-8").splitlines()
        if line.startswith(("  - ", "    ")) and ":" in line and not line.startswith("      ")
    ]
    assert keys == ["id", "name", "client", "status", "categories", "budget_hours", "rates"]
