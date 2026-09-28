"""FR-17 to FR-22, FR-49, FR-54 and FR-60: the summaries themselves.

The report functions are pure, so these tests build their own entries rather
than going through storage.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from cubit.core import (
    UNCATEGORIZED,
    Amount,
    BudgetStatus,
    Entry,
    Project,
    Rate,
    category_report,
    client_report,
    project_report,
    summarize,
    total_amount,
)


@pytest.fixture
def projects() -> dict[str, Project]:
    return {
        "acme-web": Project(
            id="acme-web",
            name="Acme website",
            client="Acme Corp",
            budget_hours=Decimal("10"),
            rates=[Rate(valid_from=date(2026, 1, 1), rate=Decimal("100"))],
        ),
        "acme-app": Project(
            id="acme-app",
            name="Acme app",
            client="Acme Corp",
            rates=[Rate(valid_from=date(2026, 1, 1), rate=Decimal("60"))],
        ),
        "internal": Project(id="internal", name="Internal work", client="IceCube Solutions"),
    }


def _entry(entry_id: str, day: date, project: str, minutes: int, category: str | None) -> Entry:
    return Entry(
        id=entry_id,
        date=day,
        duration_minutes=minutes,
        project_id=project,
        category=category,
    )


@pytest.fixture
def entries() -> list[Entry]:
    """A fortnight of work, either side of a month boundary."""
    return [
        _entry("000001", date(2026, 8, 31), "acme-web", 60, "software-coding"),
        _entry("000002", date(2026, 9, 1), "acme-web", 120, "software-coding"),
        _entry("000003", date(2026, 9, 1), "internal", 30, "admin"),
        _entry("000004", date(2026, 9, 2), "acme-app", 60, "project-management"),
        _entry("000005", date(2026, 9, 3), "acme-web", 90, None),
        _entry("000006", date(2026, 9, 10), "acme-web", 60, "software-coding"),
    ]


# ------------------------------------------------------------- amounts


def test_total_amount_keeps_unrated_time_apart(entries, projects) -> None:
    """FR-15: unrated time is not zero-rated."""
    amount = total_amount(entries, projects)

    assert amount.minutes == 420
    assert amount.hours == Decimal("7.00")
    assert amount.unrated_minutes == 30  # the internal entry
    assert amount.earnings == Decimal("610.00")  # 330m at 100 + 60m at 60
    assert not amount.is_fully_rated
    assert amount.has_earnings


def test_an_empty_amount() -> None:
    amount = Amount()
    assert amount.minutes == 0
    assert amount.hours == Decimal("0.00")
    assert amount.is_fully_rated
    assert not amount.has_earnings


def test_an_entry_for_an_unknown_project_counts_as_unrated(projects) -> None:
    amount = total_amount([_entry("000001", date(2026, 9, 1), "ghost", 60, None)], projects)
    assert amount.minutes == 60
    assert amount.unrated_minutes == 60


# ------------------------------------------------------------ summarize


def test_summarize_totals_only_the_period(entries, projects) -> None:
    """FR-18: a month summary leaves the previous month out."""
    summary = summarize(entries, projects, start=date(2026, 9, 1), end=date(2026, 9, 30))

    assert summary.total.minutes == 360  # the 31 August hour is not counted
    assert len(summary.entries) == 5


def test_summarize_by_project_is_biggest_first(entries, projects) -> None:
    """FR-17, FR-18."""
    summary = summarize(entries, projects, start=date(2026, 9, 1), end=date(2026, 9, 30))

    assert [line.key for line in summary.by_project] == ["acme-web", "acme-app", "internal"]
    assert [line.label for line in summary.by_project][0] == "Acme website"
    assert summary.by_project[0].amount.minutes == 270


def test_summarize_by_client(entries, projects) -> None:
    """FR-18: a month breaks down by client too."""
    summary = summarize(entries, projects, start=date(2026, 9, 1), end=date(2026, 9, 30))

    assert [line.label for line in summary.by_client] == ["Acme Corp", "IceCube Solutions"]
    assert summary.by_client[0].amount.minutes == 330
    assert summary.by_client[1].amount.unrated_minutes == 30


def test_summarize_leaves_out_the_days_nothing_was_logged(entries, projects) -> None:
    """FR-17: a week lists the days worked, not every day of it."""
    summary = summarize(entries, projects, start=date(2026, 8, 31), end=date(2026, 9, 6))

    assert [line.key for line in summary.by_day] == [
        "2026-08-31",
        "2026-09-01",
        "2026-09-02",
        "2026-09-03",
    ]
    assert summary.by_day[0].amount.minutes == 60


def test_summarize_by_day_over_a_month_lists_only_the_days_worked(entries, projects) -> None:
    summary = summarize(entries, projects, start=date(2026, 9, 1), end=date(2026, 9, 30))
    assert [line.key for line in summary.by_day] == [
        "2026-09-01",
        "2026-09-02",
        "2026-09-03",
        "2026-09-10",
    ]


def test_summarize_by_week_leaves_out_the_quiet_weeks(entries, projects) -> None:
    """FR-18: a month's weeks with something logged, in order."""
    summary = summarize(entries, projects, start=date(2026, 9, 1), end=date(2026, 9, 30))

    assert [line.key for line in summary.by_week] == ["2026-W36", "2026-W37"]
    assert summary.by_week[0].amount.minutes == 300  # 1 to 3 September
    assert summary.by_week[1].amount.minutes == 60  # 10 September


def test_summarize_by_category_across_projects(entries, projects) -> None:
    """FR-60: one total per category name, whatever project it was logged on."""
    summary = summarize(entries, projects, start=date(2026, 9, 1), end=date(2026, 9, 30))

    totals = {line.key: line.amount.minutes for line in summary.by_category}
    assert totals == {
        "software-coding": 180,
        "": 90,
        "project-management": 60,
        "admin": 30,
    }
    assert summary.by_category[1].label == UNCATEGORIZED


def test_summarize_breaks_each_project_down_by_category(entries, projects) -> None:
    """FR-54."""
    summary = summarize(entries, projects, start=date(2026, 9, 1), end=date(2026, 9, 30))

    acme = summary.by_project_category["acme-web"]
    assert [(line.key, line.amount.minutes) for line in acme] == [
        ("software-coding", 180),
        ("", 90),
    ]
    assert [line.key for line in summary.by_project_category["internal"]] == ["admin"]


def test_summarize_a_period_with_nothing_in_it(projects) -> None:
    summary = summarize([], projects, start=date(2026, 9, 1), end=date(2026, 9, 30))
    assert summary.total.minutes == 0
    assert summary.by_project == []
    assert summary.by_day == []
    assert summary.by_week == []


# -------------------------------------------------------- project report


def test_project_report_separates_the_period_from_the_whole_history(entries, projects) -> None:
    """FR-19: total hours and hours in the selected period."""
    report = project_report(
        projects["acme-web"],
        entries,
        projects,
        start=date(2026, 9, 1),
        end=date(2026, 9, 30),
    )

    assert report.total.minutes == 330  # includes 31 August
    assert report.period.minutes == 270
    assert report.period.earnings == Decimal("450.00")
    assert {entry.project_id for entry in report.entries} == {"acme-web"}


def test_project_report_breaks_down_by_category_with_uncategorized(entries, projects) -> None:
    """FR-49."""
    report = project_report(projects["acme-web"], entries, projects)

    assert [(line.key, line.amount.minutes) for line in report.by_category] == [
        ("software-coding", 240),
        ("", 90),
    ]
    assert report.by_category[1].label == UNCATEGORIZED
    assert report.by_category[0].amount.earnings == Decimal("400.00")


def test_project_report_budget_is_measured_against_the_whole_project(entries, projects) -> None:
    """FR-19: a budget covers the project, not the report's period."""
    report = project_report(
        projects["acme-web"],
        entries,
        projects,
        start=date(2026, 9, 10),
        end=date(2026, 9, 10),
    )

    assert report.period.minutes == 60
    assert report.budget is not None
    assert report.budget.used_minutes == 330  # every hour ever logged


def test_project_report_without_a_budget(entries, projects) -> None:
    assert project_report(projects["internal"], entries, projects).budget is None


# --------------------------------------------------------------- budget


def test_budget_percentages_and_remainder() -> None:
    """FR-19."""
    status = BudgetStatus(budget_minutes=600, used_minutes=150)
    assert status.percent_used == Decimal("25.0")
    assert status.remaining_minutes == 450
    assert status.state == "ok"


@pytest.mark.parametrize(
    ("used", "state"),
    [(479, "ok"), (480, "warning"), (599, "warning"), (600, "warning"), (601, "over")],
)
def test_budget_warns_at_the_threshold_and_over(used: int, state: str) -> None:
    """FR-22: a warning at the threshold, and again once it is exceeded."""
    status = BudgetStatus(budget_minutes=600, used_minutes=used, warning_percent=80)
    assert status.state == state


def test_the_budget_threshold_is_configurable() -> None:
    """FR-22."""
    status = BudgetStatus(budget_minutes=600, used_minutes=300, warning_percent=50)
    assert status.state == "warning"
    assert BudgetStatus(budget_minutes=600, used_minutes=300).state == "ok"


def test_an_exceeded_budget_reports_how_far_over() -> None:
    status = BudgetStatus(budget_minutes=600, used_minutes=750)
    assert status.is_over
    assert not status.is_warning
    assert status.remaining_minutes == -150
    assert status.percent_used == Decimal("125.0")


# --------------------------------------------------- client and category


def test_client_report_spans_the_clients_projects(entries, projects) -> None:
    """FR-20."""
    report = client_report("Acme Corp", entries, projects)

    assert [project.id for project in report.projects] == ["acme-app", "acme-web"]
    assert report.total.minutes == 390
    assert report.total.earnings == Decimal("610.00")
    assert [line.key for line in report.by_project] == ["acme-web", "acme-app"]


def test_client_report_matches_the_name_case_insensitively(entries, projects) -> None:
    assert client_report("acme corp", entries, projects).client == "Acme Corp"


def test_client_report_for_an_unknown_client_is_empty(entries, projects) -> None:
    report = client_report("Nobody", entries, projects)
    assert report.projects == []
    assert report.total.minutes == 0


def test_client_report_honours_the_period(entries, projects) -> None:
    """FR-21."""
    report = client_report(
        "Acme Corp", entries, projects, start=date(2026, 9, 1), end=date(2026, 9, 2)
    )
    assert report.total.minutes == 180


def test_category_report_totals_one_name_across_projects(projects) -> None:
    """FR-61."""
    entries = [
        _entry("000001", date(2026, 9, 1), "acme-web", 60, "project-management"),
        _entry("000002", date(2026, 9, 1), "acme-app", 30, "project-management"),
        _entry("000003", date(2026, 9, 1), "acme-web", 60, "software-coding"),
    ]
    report = category_report("#Project Management", entries, projects)

    assert report.category == "project-management"
    assert report.total.minutes == 90
    assert [(line.key, line.amount.minutes) for line in report.by_project] == [
        ("acme-web", 60),
        ("acme-app", 30),
    ]


def test_category_report_can_total_uncategorized_time(entries, projects) -> None:
    """FR-49: uncategorized is a bucket like any other."""
    report = category_report("", entries, projects)
    assert report.category == UNCATEGORIZED
    assert report.total.minutes == 90
