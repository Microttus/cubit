"""FR-43 to FR-48 and FR-52: category normalization, ranking and the typo guard."""

from __future__ import annotations

from datetime import date, time

import pytest

from cubit.core import (
    CategoryError,
    Entry,
    Project,
    closest_category,
    display_category,
    normalize_category,
    normalize_optional_category,
    rank_categories,
    suggest_categories,
)
from cubit.core.categories import is_normalized


@pytest.mark.parametrize(
    ("raw", "slug"),
    [
        ("Project Management", "project-management"),
        ("project management", "project-management"),
        ("#project-management", "project-management"),
        ("  #Project   Management  ", "project-management"),
        ("PROJECT_MANAGEMENT", "project-management"),
        ("software-coding", "software-coding"),
        ("Møter", "moter"),
        ("Forbedring av UX", "forbedring-av-ux"),
        ("r&d", "r-d"),
        ("a" * 40, "a" * 40),
    ],
)
def test_normalize_category(raw: str, slug: str) -> None:
    """FR-48: names normalize to a lowercase slug."""
    assert normalize_category(raw) == slug


@pytest.mark.parametrize("raw", ["", "   ", "#", "###", "!!!", "a" * 41, "-"])
def test_normalize_category_rejects_unusable_names(raw: str) -> None:
    with pytest.raises(CategoryError):
        normalize_category(raw)


def test_normalize_optional_category_treats_blank_as_uncategorized() -> None:
    assert normalize_optional_category(None) is None
    assert normalize_optional_category("") is None
    assert normalize_optional_category("  ") is None
    assert normalize_optional_category("#Admin") == "admin"


def test_display_category_adds_the_hash() -> None:
    """FR-48: the # is display sugar only."""
    assert display_category("software-coding") == "#software-coding"
    assert display_category(None) == "-"


def test_is_normalized() -> None:
    assert is_normalized("software-coding")
    assert not is_normalized("#software-coding")
    assert not is_normalized("Software Coding")
    assert not is_normalized("a" * 41)


def _entry(entry_id: str, day: date, category: str | None, start: time | None = None) -> Entry:
    return Entry(
        id=entry_id,
        date=day,
        start=start,
        end=None if start is None else time(start.hour + 1, start.minute),
        duration_minutes=60,
        project_id="acme-web",
        category=category,
    )


def test_rank_categories_orders_by_recency_then_frequency_then_name() -> None:
    """FR-46: most recent use, then frequency, then unused alphabetically."""
    entries = [
        _entry("000001", date(2026, 9, 1), "testing"),
        _entry("000002", date(2026, 9, 1), "software-coding"),
        _entry("000003", date(2026, 9, 2), "software-coding"),
        _entry("000004", date(2026, 9, 2), "testing"),
        _entry("000005", date(2026, 9, 3), "project-management"),
    ]
    registered = ["software-coding", "project-management", "testing", "admin", "zeta", "billing"]

    assert rank_categories(registered, entries) == [
        "project-management",  # used most recently
        "software-coding",  # same last day and same count as testing, so by name
        "testing",
        "admin",  # registered but unused, alphabetically
        "billing",
        "zeta",
    ]


def test_rank_categories_breaks_a_recency_tie_on_frequency() -> None:
    entries = [
        _entry("000001", date(2026, 9, 1), "rare"),
        _entry("000002", date(2026, 9, 2), "rare"),
        _entry("000003", date(2026, 9, 2), "common"),
        _entry("000004", date(2026, 9, 2), "common"),
        _entry("000005", date(2026, 9, 2), "common"),
    ]
    assert rank_categories(["rare", "common"], entries)[:2] == ["common", "rare"]


def test_rank_categories_uses_start_time_within_a_day() -> None:
    entries = [
        _entry("000001", date(2026, 9, 2), "morning", time(8, 0)),
        _entry("000002", date(2026, 9, 2), "evening", time(20, 0)),
    ]
    assert rank_categories(["morning", "evening"], entries) == ["evening", "morning"]


def test_rank_categories_ignores_uncategorized_entries() -> None:
    entries = [_entry("000001", date(2026, 9, 2), None)]
    assert rank_categories(["admin"], entries) == ["admin"]


def test_rank_categories_suggests_a_used_but_unregistered_name() -> None:
    """Hand-edited CSVs can hold a category the project list has not caught up with."""
    entries = [_entry("000001", date(2026, 9, 2), "hotfix")]
    assert rank_categories(["admin"], entries) == ["hotfix", "admin"]


def test_rank_categories_without_history_is_alphabetical() -> None:
    assert rank_categories(["testing", "admin", "coding"]) == ["admin", "coding", "testing"]


def test_suggest_categories_only_uses_the_selected_project(storage) -> None:
    """FR-47: suggestions come from this project's own history."""
    projects = storage.load_projects_map()
    entries = storage.load_all_entries()

    acme = suggest_categories(projects["acme-web"], entries)
    assert acme[0] == "software-coding"  # most recent use in the sample data
    assert "admin" not in acme  # belongs to the internal project

    internal = suggest_categories(projects["internal"], entries)
    assert internal == ["admin"]


def test_suggest_categories_respects_the_limit(storage) -> None:
    project = storage.get_project("acme-web")
    assert len(suggest_categories(project, storage.load_all_entries(), limit=2)) == 2


def test_closest_category_finds_a_typo() -> None:
    """FR-52: an unregistered name close to a registered one is flagged."""
    registered = ["software-coding", "project-management"]
    assert closest_category("software-codng", registered) == "software-coding"
    assert closest_category("Software Codin", registered) == "software-coding"


def test_closest_category_is_quiet_when_nothing_is_close() -> None:
    registered = ["software-coding", "project-management"]
    assert closest_category("invoicing", registered) is None
    assert closest_category("software-coding", registered) is None


def test_project_with_category_appends_without_duplicating() -> None:
    """FR-45: using a new category registers it; using a known one changes nothing."""
    project = Project(id="acme-web", name="Acme website", categories=["software-coding"])

    grown = project.with_category("#Testing")
    assert grown.categories == ["software-coding", "testing"]

    assert project.with_category("software-coding") is project
