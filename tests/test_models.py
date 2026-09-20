"""The models mirror REQUIREMENTS section 4: ids, slugs, times and money."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest
from pydantic import ValidationError

from cubit.core import Config, Entry, Project, ProjectStatus, Rate, TimerState


def test_entry_id_must_be_six_hex_characters() -> None:
    with pytest.raises(ValidationError, match="six hex"):
        Entry(id="xyz", date=date(2026, 9, 18), duration_minutes=30, project_id="acme-web")


def test_entry_duration_must_be_at_least_one_minute() -> None:
    with pytest.raises(ValidationError):
        Entry(id="a3f9c1", date=date(2026, 9, 18), duration_minutes=0, project_id="acme-web")


def test_entry_times_come_in_pairs() -> None:
    """Both blank or both set: REQUIREMENTS 4.1."""
    with pytest.raises(ValidationError, match="both"):
        Entry(
            id="a3f9c1",
            date=date(2026, 9, 18),
            start=time(9, 0),
            duration_minutes=30,
            project_id="acme-web",
        )


def test_entry_normalizes_its_category() -> None:
    """FR-48: normalization happens in one place and the model goes through it."""
    entry = Entry(
        id="a3f9c1",
        date=date(2026, 9, 18),
        duration_minutes=30,
        project_id="acme-web",
        category="#Project Management",
    )
    assert entry.category == "project-management"


def test_entry_blank_category_means_uncategorized() -> None:
    entry = Entry(
        id="a3f9c1",
        date=date(2026, 9, 18),
        duration_minutes=30,
        project_id="acme-web",
        category="  ",
    )
    assert entry.category is None


def test_entry_sort_key_is_date_start_id() -> None:
    """FR-42: stable write order."""
    entry = Entry(
        id="a3f9c1",
        date=date(2026, 9, 18),
        start=time(9, 5),
        end=time(10, 35),
        duration_minutes=90,
        project_id="acme-web",
    )
    assert entry.sort_key == (date(2026, 9, 18), time(9, 5), "a3f9c1")

    timeless = entry.model_copy(update={"start": None, "end": None, "id": "000001"})
    assert timeless.sort_key == (date(2026, 9, 18), time(0, 0), "000001")


@pytest.mark.parametrize("bad_id", ["Acme-Web", "acme_web", "acme web", "-acme", "acme-", ""])
def test_project_id_must_be_a_lowercase_slug(bad_id: str) -> None:
    """FR-12: the id is a unique lowercase slug."""
    with pytest.raises(ValidationError):
        Project(id=bad_id, name="Acme website")


def test_project_defaults_to_active_and_no_budget() -> None:
    project = Project(id="acme-web", name="Acme website")
    assert project.status is ProjectStatus.ACTIVE
    assert project.is_active
    assert project.budget_hours is None
    assert project.budget_minutes is None


def test_project_budget_in_minutes() -> None:
    project = Project(id="acme-web", name="Acme website", budget_hours=Decimal("120.5"))
    assert project.budget_minutes == 7230


def test_project_categories_are_normalized_and_deduplicated() -> None:
    project = Project(
        id="acme-web",
        name="Acme website",
        categories=["#Software Coding", "software-coding", "Testing"],
    )
    assert project.categories == ["software-coding", "testing"]


def test_project_rejects_unknown_keys() -> None:
    """A typo in projects.yaml is an error, not a silently ignored key."""
    with pytest.raises(ValidationError):
        Project(id="acme-web", name="Acme website", budgets_hours=10)


def test_rate_from_a_yaml_float_is_exact() -> None:
    assert Rate(valid_from=date(2026, 1, 1), rate=80.5).rate == Decimal("80.5")


def test_config_defaults_match_the_documented_ones() -> None:
    config = Config()
    assert config.currency == "NOK"  # cubit is built for a Norwegian company
    assert config.week_starts_on == "monday"
    assert config.budget_warning_percent == 80
    assert config.prompt_for_category is True
    assert config.theme == "dark"
    assert config.menubar_title == "time"


def test_the_currency_is_a_setting_not_a_fixture() -> None:
    """The default suits IceCube Solutions; anyone else changes one line."""
    assert Config(currency="EUR").currency == "EUR"
    assert Config(currency="USD").currency == "USD"


def test_config_rejects_an_unknown_theme() -> None:
    with pytest.raises(ValidationError):
        Config(theme="neon")


def test_config_accepts_capitalised_values() -> None:
    assert Config(theme="Dark", week_starts_on="Monday").theme == "dark"


def test_timer_state_requires_a_utc_offset() -> None:
    """REQUIREMENTS 4.4: started_at is timezone-aware so DST cannot skew it."""
    with pytest.raises(ValidationError, match="UTC offset"):
        TimerState(project_id="acme-web", started_at=datetime(2026, 9, 18, 9, 5))

    state = TimerState(
        project_id="acme-web",
        started_at=datetime(2026, 9, 18, 9, 5, tzinfo=UTC),
    )
    assert state.started_at.utcoffset() is not None
    assert state.category is None
    assert state.note == ""
