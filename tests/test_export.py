"""FR-23: a report as CSV or Markdown."""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal

import pytest

from cubit.core import (
    FORMATS,
    CubitError,
    Entry,
    Project,
    Rate,
    category_document,
    category_report,
    client_document,
    client_report,
    project_document,
    project_report,
    render,
    summarize,
    summary_document,
    to_csv,
    to_markdown,
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
        "internal": Project(id="internal", name="Internal work", client="IceCube Solutions"),
    }


@pytest.fixture
def entries() -> list[Entry]:
    return [
        Entry(
            id="000001",
            date=date(2026, 9, 1),
            duration_minutes=120,
            project_id="acme-web",
            category="software-coding",
            note="Layout work",
        ),
        Entry(
            id="000002",
            date=date(2026, 9, 2),
            duration_minutes=30,
            project_id="internal",
            note="Admin, and filing",
        ),
    ]


@pytest.fixture
def summary(entries, projects):
    return summarize(entries, projects, start=date(2026, 9, 1), end=date(2026, 9, 30))


def test_the_formats_are_the_documented_ones() -> None:
    assert list(FORMATS) == ["text", "csv", "markdown"]


def test_csv_keeps_its_sections_apart(summary, projects) -> None:
    document = summary_document(summary, kind="month", label="September 2026", currency="EUR")
    rows = list(csv.reader(io.StringIO(to_csv(document))))

    assert rows[0] == ["September 2026"]
    assert "2026-09-01 to 2026-09-30" in rows[1][0]
    # A blank line, then the section name, then its heading row.
    assert [] in rows
    assert ["Project"] in rows
    assert ["Project", "Time", "Hours", "Earned (EUR)", "Unrated"] in rows


def test_csv_rows_carry_the_numbers(summary, projects) -> None:
    document = summary_document(summary, kind="month", label="September", currency="EUR")
    rows = list(csv.reader(io.StringIO(to_csv(document))))

    acme = next(row for row in rows if row and row[0] == "Acme website")
    assert acme == ["Acme website", "2h", "2.00", "200.00", ""]

    internal = next(row for row in rows if row and row[0] == "Internal work")
    assert internal == ["Internal work", "30m", "0.50", "", "30m"]


def test_csv_quotes_a_note_with_a_comma(summary, projects) -> None:
    document = summary_document(
        summary,
        kind="month",
        label="September",
        currency="EUR",
        projects=projects,
        entries=True,
    )
    rows = list(csv.reader(io.StringIO(to_csv(document))))
    note = next(row for row in rows if row and row[0] == "000002")
    assert note[-1] == "Admin, and filing"


def test_markdown_is_a_table_per_section(summary) -> None:
    text = to_markdown(
        summary_document(summary, kind="week", label="Week 36, 2026", currency="EUR")
    )

    assert text.startswith("# Week 36, 2026")
    assert "## Project" in text
    assert "## Day" in text
    assert "## Category" in text
    assert "| Project | Time | Hours | Earned (EUR) | Unrated |" in text
    assert "|---|---|---|---|---|" in text
    assert "| Acme website | 2h | 2.00 | 200.00 |  |" in text


def test_markdown_escapes_a_pipe_in_a_note(projects) -> None:
    entries = [
        Entry(
            id="000001",
            date=date(2026, 9, 1),
            duration_minutes=60,
            project_id="acme-web",
            note="a | b",
        )
    ]
    summary = summarize(entries, projects, start=date(2026, 9, 1), end=date(2026, 9, 30))
    text = to_markdown(
        summary_document(
            summary, kind="week", label="W", currency="EUR", projects=projects, entries=True
        )
    )
    assert r"a \| b" in text


def test_a_month_and_a_week_show_different_sections(summary) -> None:
    """FR-17 and FR-18 ask for different breakdowns."""
    week = to_markdown(summary_document(summary, kind="week", label="W", currency="EUR"))
    month = to_markdown(summary_document(summary, kind="month", label="M", currency="EUR"))

    assert "## Day" in week and "## Week" not in week
    assert "## Week" in month and "## Client" in month
    assert "## Day" not in month


def test_the_subtitle_flags_unrated_time(summary) -> None:
    """FR-15."""
    document = summary_document(summary, kind="month", label="September", currency="EUR")
    assert "200.00 EUR + 30m unrated" in document.subtitle


def test_the_subtitle_of_a_fully_rated_report(projects) -> None:
    entries = [
        Entry(id="000001", date=date(2026, 9, 1), duration_minutes=60, project_id="acme-web")
    ]
    summary = summarize(entries, projects, start=date(2026, 9, 1), end=date(2026, 9, 30))
    document = summary_document(summary, kind="month", label="September", currency="EUR")

    assert "100.00 EUR" in document.subtitle
    assert "unrated" not in document.subtitle


def test_a_project_document_carries_the_budget(entries, projects) -> None:
    """FR-19, FR-22."""
    report = project_report(projects["acme-web"], entries, projects)
    text = to_markdown(project_document(report, currency="EUR", projects=projects))

    assert "# Acme website (acme-web)" in text
    assert "| Budget | 2h of 10h (20.0%) |" in text
    assert "| Remaining | 8h |" in text
    assert "## Entries" in text


def test_an_over_budget_project_says_so(projects) -> None:
    entries = [
        Entry(id="000001", date=date(2026, 9, 1), duration_minutes=700, project_id="acme-web")
    ]
    report = project_report(projects["acme-web"], entries, projects)
    text = to_markdown(project_document(report, currency="EUR", projects=projects))

    assert "| Over budget | 1h40m |" in text


def test_a_client_document(entries, projects) -> None:
    """FR-20."""
    report = client_report("Acme Corp", entries, projects)
    text = to_markdown(client_document(report, currency="EUR"))

    assert text.startswith("# Acme Corp")
    assert "| Acme website | 2h |" in text


def test_a_category_document(entries, projects) -> None:
    """FR-61."""
    report = category_report("software-coding", entries, projects)
    text = to_markdown(category_document(report, currency="EUR"))

    assert text.startswith("# #software-coding")
    assert "| Acme website | 2h |" in text


def test_render_picks_the_format(summary) -> None:
    document = summary_document(summary, kind="week", label="W", currency="EUR")
    assert render(document, "markdown").startswith("# W")
    assert render(document, "csv").startswith("W\r\n") or render(document, "csv").startswith("W\n")


def test_render_rejects_an_unknown_format(summary) -> None:
    document = summary_document(summary, kind="week", label="W", currency="EUR")
    with pytest.raises(CubitError) as caught:
        render(document, "pdf")
    assert "text, csv, markdown" in (caught.value.hint or "")


def test_an_empty_report_still_exports(projects) -> None:
    summary = summarize([], projects, start=date(2026, 9, 1), end=date(2026, 9, 30))
    document = summary_document(summary, kind="month", label="September", currency="EUR")

    assert "## Project" in to_markdown(document)
    assert to_csv(document).startswith("September")
