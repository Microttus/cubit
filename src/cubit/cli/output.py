"""Terminal formatting: aligned tables, totals and a sparing use of colour.

FR-28 wants summaries that line up in a terminal; FR-59 wants the accent used
sparingly and ``NO_COLOR`` respected. Columns are padded here rather than by a
table library, so output does not change with the width of the window.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal

import typer

from cubit.core import (
    Amount,
    BudgetStatus,
    Entry,
    Line,
    Project,
    display_category,
    format_duration,
    format_hours,
)

#: Cubit's cyan accent, the terminal's nearest equivalent of --color-accent.
ACCENT = typer.colors.CYAN
MUTED = typer.colors.BRIGHT_BLACK
WARNING = typer.colors.YELLOW
DANGER = typer.colors.RED


def colors_enabled() -> bool:
    """False when NO_COLOR is set or output is not a terminal (FR-59)."""
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def paint(text: str, color: str) -> str:
    """Colour ``text``, or return it untouched when colour is off."""
    return typer.style(text, fg=color) if colors_enabled() else text


def accent(text: str) -> str:
    return paint(text, ACCENT)


def muted(text: str) -> str:
    return paint(text, MUTED)


def echo(message: str = "") -> None:
    typer.echo(message)


def warn(message: str) -> None:
    """A note on stderr that is not an error."""
    typer.echo(paint(message, WARNING), err=True)


@dataclass(frozen=True)
class Column:
    """One column of a table: its heading, how to read it, how to align it."""

    heading: str
    align: str = "left"


def table(columns: Sequence[Column], rows: Sequence[Sequence[str]]) -> str:
    """Render rows as aligned columns, with a muted heading line.

    Widths come from the content, so a table is stable no matter how wide the
    terminal is.
    """
    if not rows:
        return ""

    cells = [[str(value) for value in row] for row in rows]
    widths = [
        max(len(column.heading), *(len(row[index]) for row in cells))
        for index, column in enumerate(columns)
    ]

    lines = [
        muted(
            "  ".join(
                _pad(column.heading, widths[index], "left") for index, column in enumerate(columns)
            ).rstrip()
        )
    ]
    for row in cells:
        lines.append(
            "  ".join(
                _pad(row[index], widths[index], column.align)
                for index, column in enumerate(columns)
            ).rstrip()
        )
    return "\n".join(lines)


def _pad(text: str, width: int, align: str) -> str:
    return text.rjust(width) if align == "right" else text.ljust(width)


def format_date(value: date) -> str:
    return value.isoformat()


def format_time(value: time | None) -> str:
    return "" if value is None else f"{value.hour:02d}:{value.minute:02d}"


def format_total(minutes: int) -> str:
    """A total as both a duration and decimal hours, e.g. ``7h30m (7.50 h)``."""
    return f"{format_duration(minutes)} ({format_hours(minutes)} h)"


def entry_rows(entries: Iterable[Entry], projects: dict[str, Project]) -> list[list[str]]:
    """Rows for the entry table, project shown by name with the id as backup."""
    rows = []
    for entry in entries:
        project = projects.get(entry.project_id)
        rows.append(
            [
                entry.id,
                format_date(entry.date),
                format_time(entry.start),
                format_time(entry.end),
                format_duration(entry.duration_minutes),
                project.name if project else f"{entry.project_id} (unknown)",
                display_category(entry.category),
                entry.note,
                format_date(entry.billed_on) if entry.billed_on else "",
            ]
        )
    return rows


ENTRY_COLUMNS = (
    Column("ID"),
    Column("DATE"),
    Column("START", "right"),
    Column("END", "right"),
    Column("TIME", "right"),
    Column("PROJECT"),
    Column("CATEGORY"),
    Column("NOTE"),
    Column("BILLED"),
)


def format_money(value: Decimal, currency: str) -> str:
    """An amount with its currency, e.g. ``1250.00 EUR``."""
    return f"{value:.2f} {currency}"


def format_earnings(amount: Amount, currency: str) -> str:
    """Money earned, saying plainly when some of the time had no rate (FR-15)."""
    if not amount.has_earnings and not amount.is_fully_rated:
        return "unrated"
    money = format_money(amount.earnings, currency)
    if amount.is_fully_rated:
        return money
    return f"{money} + {format_duration(amount.unrated_minutes)} unrated"


def breakdown_table(lines: Sequence[Line], heading: str, currency: str) -> str:
    """One breakdown of a report: label, time, share and earnings.

    Unrated time gets its own column, and only when there is some, so money
    still lines up in the EARNED column instead of being pushed sideways by a
    trailing note (FR-15, FR-28).
    """
    total = sum(line.amount.minutes for line in lines)
    any_unrated = any(line.amount.unrated_minutes for line in lines)

    columns = [
        Column(heading),
        Column("TIME", "right"),
        Column("HOURS", "right"),
        Column("SHARE", "right"),
        Column(f"EARNED ({currency})", "right"),
    ]
    if any_unrated:
        columns.append(Column("UNRATED", "right"))

    rows = []
    for line in lines:
        amount = line.amount
        row = [
            line.label,
            format_duration(amount.minutes),
            format_hours(amount.minutes),
            _share(amount.minutes, total),
            f"{amount.earnings:.2f}" if amount.has_earnings else "-",
        ]
        if any_unrated:
            row.append(format_duration(amount.unrated_minutes) if amount.unrated_minutes else "-")
        rows.append(row)
    return table(tuple(columns), rows)


def _share(minutes: int, total: int) -> str:
    if total <= 0:
        return "-"
    return f"{Decimal(minutes) * 100 / Decimal(total):.0f}%"


def budget_line(status: BudgetStatus) -> str:
    """The budget, coloured by how close it is to running out (FR-22)."""
    used = format_duration(status.used_minutes)
    budget = format_duration(status.budget_minutes)
    text = f"{used} of {budget} ({status.percent_used}%)"

    if status.is_over:
        over = format_duration(-status.remaining_minutes)
        return paint(f"{text}, {over} over budget", DANGER)
    remaining = f"{format_duration(status.remaining_minutes)} left"
    if status.is_warning:
        return paint(f"{text}, {remaining}", WARNING)
    return f"{text}, {remaining}"


def heading(text: str) -> str:
    """A section heading, in the accent colour."""
    return accent(text)
