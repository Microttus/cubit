"""FR-14 and FR-15: rate lookup by date, and unrated time."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from cubit.core import Entry, Project, Rate, earnings, earnings_for_entry, is_unrated, rate_for_date
from cubit.core.rates import total_earnings


@pytest.fixture
def project() -> Project:
    return Project(
        id="acme-web",
        name="Acme website",
        rates=[
            Rate(valid_from=date(2026, 1, 1), rate=Decimal("95")),
            Rate(valid_from=date(2026, 7, 1), rate=Decimal("105")),
        ],
    )


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2025, 12, 31), None),  # before the first rate started
        (date(2026, 1, 1), Decimal("95")),  # the day it starts counts
        (date(2026, 6, 30), Decimal("95")),  # the day before the raise
        (date(2026, 7, 1), Decimal("105")),  # the raise applies at once
        (date(2030, 1, 1), Decimal("105")),  # the last rate keeps applying
    ],
)
def test_rate_for_date(project: Project, day: date, expected: Decimal | None) -> None:
    """FR-14: the latest rate with valid_from on or before the entry date."""
    assert rate_for_date(project, day) == expected


def test_rate_lookup_is_independent_of_the_order_in_the_file() -> None:
    """A hand-edited projects.yaml may list the rates in any order."""
    project = Project(
        id="acme-web",
        name="Acme website",
        rates=[
            Rate(valid_from=date(2026, 7, 1), rate=Decimal("105")),
            Rate(valid_from=date(2026, 1, 1), rate=Decimal("95")),
        ],
    )
    assert [rate.valid_from for rate in project.rates] == [date(2026, 1, 1), date(2026, 7, 1)]
    assert rate_for_date(project, date(2026, 3, 1)) == Decimal("95")


def test_two_rates_on_the_same_day_are_rejected() -> None:
    with pytest.raises(ValueError, match="valid_from"):
        Project(
            id="acme-web",
            name="Acme website",
            rates=[
                Rate(valid_from=date(2026, 1, 1), rate=Decimal("95")),
                Rate(valid_from=date(2026, 1, 1), rate=Decimal("105")),
            ],
        )


def test_project_without_rates_is_unrated(project: Project) -> None:
    """FR-15: no rate means no earnings, not zero earnings."""
    internal = Project(id="internal", name="Internal work")
    entry = Entry(id="b71c02", date=date(2026, 9, 18), duration_minutes=45, project_id="internal")
    assert rate_for_date(internal, entry.date) is None
    assert earnings_for_entry(internal, entry) is None
    assert is_unrated(internal, entry)


def test_earnings_use_the_rate_of_the_entry_date(project: Project) -> None:
    before = Entry(id="000001", date=date(2026, 6, 30), duration_minutes=90, project_id="acme-web")
    after = Entry(id="000002", date=date(2026, 7, 1), duration_minutes=90, project_id="acme-web")

    assert earnings_for_entry(project, before) == Decimal("142.50")
    assert earnings_for_entry(project, after) == Decimal("157.50")
    assert not is_unrated(project, after)


def test_earnings_round_to_cents_and_stay_decimal() -> None:
    value = earnings(50, Decimal("95"))
    assert isinstance(value, Decimal)
    assert value == Decimal("79.17")  # 50/60 * 95 = 79.1666...


def test_earnings_of_unrated_minutes_is_none() -> None:
    assert earnings(90, None) is None


def test_total_earnings_keeps_unrated_minutes_separate(project: Project) -> None:
    """FR-15: unrated time is reported as minutes, never folded into the money."""
    internal = Project(id="internal", name="Internal work")
    entries = [
        Entry(id="000001", date=date(2026, 7, 1), duration_minutes=60, project_id="acme-web"),
        Entry(id="000002", date=date(2026, 7, 1), duration_minutes=45, project_id="internal"),
        Entry(id="000003", date=date(2025, 1, 1), duration_minutes=30, project_id="acme-web"),
        Entry(id="000004", date=date(2026, 7, 1), duration_minutes=15, project_id="gone"),
    ]
    total, unrated = total_earnings(entries, {"acme-web": project, "internal": internal})

    assert total == Decimal("105.00")
    assert unrated == 90  # 45 internal + 30 before any rate + 15 unknown project


def test_rates_from_yaml_floats_stay_exact(storage) -> None:
    """Money is Decimal: 80.50 in the file must not become 80.4999...."""
    archived = storage.get_project("old-site")
    assert archived.rates[0].rate == Decimal("80.50")
    assert earnings(60, archived.rates[0].rate) == Decimal("80.50")
