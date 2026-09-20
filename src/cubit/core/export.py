"""Turning a report into CSV or Markdown (FR-23).

A report is a handful of named tables; the CLI draws them with padding, the web
app with ``<table>``, and this module writes them as text you can send someone
or open in a spreadsheet. The shape of a table is decided here so the two
interfaces cannot drift apart, and every function is pure.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from cubit.core.categories import display_category
from cubit.core.durations import format_duration, format_hours
from cubit.core.errors import CubitError
from cubit.core.models import Entry, Project
from cubit.core.reports import (
    CategoryReport,
    ClientReport,
    Line,
    ProjectReport,
    Summary,
)

#: The formats ``--format`` accepts.
FORMATS = ("text", "csv", "markdown")


@dataclass(frozen=True)
class Table:
    """One named block of rows, with its column headings."""

    title: str
    columns: list[str]
    rows: list[list[str]]


@dataclass(frozen=True)
class Document:
    """A whole report: a title, a summary line and the tables under it."""

    title: str
    subtitle: str
    tables: list[Table]


def breakdown_table(lines: Sequence[Line], heading: str, currency: str) -> Table:
    """A breakdown as time, hours, earnings and unrated minutes."""
    return Table(
        title=heading,
        columns=[heading, "Time", "Hours", f"Earned ({currency})", "Unrated"],
        rows=[
            [
                line.label,
                format_duration(line.amount.minutes),
                format_hours(line.amount.minutes),
                _money(line.amount.earnings) if line.amount.has_earnings else "",
                format_duration(line.amount.unrated_minutes) if line.amount.unrated_minutes else "",
            ]
            for line in lines
        ],
    )


def entries_table(entries: Iterable[Entry], projects: dict[str, Project]) -> Table:
    """The entry list, in the same column order as the CSV files themselves."""
    return Table(
        title="Entries",
        columns=["Id", "Date", "Start", "End", "Time", "Project", "Category", "Note"],
        rows=[
            [
                entry.id,
                entry.date.isoformat(),
                _clock(entry.start),
                _clock(entry.end),
                format_duration(entry.duration_minutes),
                _project_name(projects, entry.project_id),
                display_category(entry.category) if entry.category else "",
                entry.note,
            ]
            for entry in entries
        ],
    )


def summary_document(
    summary: Summary,
    *,
    kind: str,
    label: str,
    currency: str,
    projects: dict[str, Project] | None = None,
    entries: bool = False,
) -> Document:
    """A weekly or monthly summary as a document (FR-17, FR-18, FR-23)."""
    tables = [breakdown_table(summary.by_project, "Project", currency)]
    if kind == "month":
        tables.append(breakdown_table(summary.by_client, "Client", currency))
        tables.append(breakdown_table(summary.by_week, "Week", currency))
    else:
        tables.append(breakdown_table(summary.by_day, "Day", currency))
    tables.append(breakdown_table(summary.by_category, "Category", currency))

    if entries:
        tables.append(entries_table(summary.entries, projects or {}))

    return Document(
        title=label,
        subtitle=_subtitle(summary.start, summary.end, summary.total, currency),
        tables=tables,
    )


def project_document(
    report: ProjectReport,
    *,
    currency: str,
    projects: dict[str, Project] | None = None,
    entries: bool = True,
) -> Document:
    """A per-project report as a document (FR-19)."""
    tables = [
        Table(
            title="Totals",
            columns=["Measure", "Value"],
            rows=_project_rows(report, currency),
        ),
        breakdown_table(report.by_category, "Category", currency),
    ]
    if entries:
        tables.append(
            entries_table(report.entries, projects or {report.project.id: report.project})
        )

    return Document(
        title=f"{report.project.name} ({report.project.id})",
        subtitle=_subtitle(report.start, report.end, report.period, currency),
        tables=tables,
    )


def client_document(report: ClientReport, *, currency: str) -> Document:
    """A per-client report as a document (FR-20)."""
    return Document(
        title=report.client,
        subtitle=_subtitle(report.start, report.end, report.total, currency),
        tables=[breakdown_table(report.by_project, "Project", currency)],
    )


def category_document(report: CategoryReport, *, currency: str) -> Document:
    """A per-category report as a document (FR-61)."""
    return Document(
        title=f"#{report.category}",
        subtitle=_subtitle(report.start, report.end, report.total, currency),
        tables=[breakdown_table(report.by_project, "Project", currency)],
    )


def to_csv(document: Document) -> str:
    """The document as CSV.

    Each table keeps its own heading row, with its title on the line above and a
    blank line between, so a spreadsheet shows the sections apart rather than
    running them together.
    """
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow([document.title])
    writer.writerow([document.subtitle])

    for table in document.tables:
        writer.writerow([])
        writer.writerow([table.title])
        writer.writerow(table.columns)
        writer.writerows(table.rows)
    return stream.getvalue()


def to_markdown(document: Document) -> str:
    """The document as Markdown tables, ready to paste into a message."""
    parts = [f"# {document.title}", "", document.subtitle, ""]
    for table in document.tables:
        parts.append(f"## {table.title}")
        parts.append("")
        parts.append("| " + " | ".join(table.columns) + " |")
        parts.append("|" + "|".join(["---"] * len(table.columns)) + "|")
        for row in table.rows:
            parts.append("| " + " | ".join(_escape(cell) for cell in row) + " |")
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def render(document: Document, fmt: str) -> str:
    """The document in the format named, for ``--format``."""
    if fmt == "csv":
        return to_csv(document)
    if fmt == "markdown":
        return to_markdown(document)
    raise CubitError(
        f"Unknown format {fmt!r}.",
        hint=f"Use one of {', '.join(FORMATS)}.",
    )


def _project_rows(report: ProjectReport, currency: str) -> list[list[str]]:
    rows = [
        ["Total", f"{format_duration(report.total.minutes)} ({report.total.hours} h)"],
    ]
    if report.start or report.end:
        rows.append(
            ["Period", f"{format_duration(report.period.minutes)} ({report.period.hours} h)"]
        )
    rows.append(["Earned", f"{_money(report.period.earnings)} {currency}".strip()])
    if report.period.unrated_minutes:
        rows.append(["Unrated", format_duration(report.period.unrated_minutes)])
    if report.budget is not None:
        budget = report.budget
        rows.append(
            [
                "Budget",
                f"{format_duration(budget.used_minutes)} of "
                f"{format_duration(budget.budget_minutes)} ({budget.percent_used}%)",
            ]
        )
        rows.append(
            [
                "Remaining" if not budget.is_over else "Over budget",
                format_duration(abs(budget.remaining_minutes)),
            ]
        )
    return rows


def _subtitle(start: date | None, end: date | None, amount, currency: str) -> str:
    period = ""
    if start and end:
        period = f"{start.isoformat()} to {end.isoformat()} · "
    elif start or end:
        period = f"{(start or end).isoformat()} · "

    money = f"{_money(amount.earnings)} {currency}".strip()
    if not amount.is_fully_rated:
        money += f" + {format_duration(amount.unrated_minutes)} unrated"
    return f"{period}{format_duration(amount.minutes)} ({amount.hours} h) · {money}"


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


def _clock(value) -> str:
    return "" if value is None else f"{value.hour:02d}:{value.minute:02d}"


def _project_name(projects: dict[str, Project], project_id: str) -> str:
    project = projects.get(project_id)
    return project.name if project else project_id


def _escape(cell: str) -> str:
    """Keep a note containing a pipe from breaking the table."""
    return cell.replace("|", "\\|")
