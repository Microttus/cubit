"""FR-80: a report as a PDF, with the Cubit logo and a made-with-Cubit footer."""

from __future__ import annotations

import re
import zlib
from datetime import date, timedelta
from pathlib import Path

from cubit.cli.exit_codes import EXIT_ERROR, EXIT_OK
from cubit.core import Document, Table, render_file, to_pdf, with_title
from cubit.core.pdf import CONTENT_WIDTH, _column_widths, _width, _wrap

GENERATED = date(2026, 9, 28)


def _document(rows: list[list[str]] | None = None) -> Document:
    return Document(
        title="September 2026",
        subtitle="2026-09-01 to 2026-09-30 · 3h (3.00 h) · 300.00 EUR",
        tables=[
            Table(
                title="Entries",
                columns=["Date", "Time", "Note", "Unrated"],
                rows=rows if rows is not None else [["2026-09-01", "3h", "Layout (v2)", ""]],
            )
        ],
    )


def _pages(pdf: bytes) -> list[str]:
    """The text drawn on each page, one string per page."""
    streams = re.findall(rb"stream\n(.*?)\nendstream", pdf, re.DOTALL)
    pages = []
    for stream in streams:
        content = zlib.decompress(stream)
        shown = re.findall(rb"\(((?:[^()\\]|\\.)*)\) Tj", content)
        pages.append("\n".join(re.sub(rb"\\(.)", rb"\1", text).decode("cp1252") for text in shown))
    return pages


def test_a_pdf_is_a_well_formed_file() -> None:
    pdf = to_pdf(_document(), generated=GENERATED)

    assert pdf.startswith(b"%PDF-1.4")
    assert pdf.rstrip().endswith(b"%%EOF")
    # Every offset in the cross-reference table points at the object it names.
    start = int(re.search(rb"startxref\n(\d+)", pdf).group(1))
    offsets = re.findall(rb"(\d{10}) 00000 n", pdf[start:])
    for number, offset in enumerate(offsets, start=1):
        assert pdf[int(offset) :].startswith(f"{number} 0 obj".encode())


def test_a_pdf_carries_the_report_the_logo_and_the_footer() -> None:
    [page] = _pages(to_pdf(_document(), generated=GENERATED))

    assert "Cubit" in page
    assert "September 2026" in page
    assert "Generated 2026-09-28" in page
    assert "Layout (v2)" in page  # brackets are escaped, and come back intact
    assert "Made with Cubit, a product of IceCube Solutions" in page
    assert "Page 1 of 1" in page


def test_a_pdf_leaves_out_columns_that_are_empty_throughout() -> None:
    [page] = _pages(to_pdf(_document(), generated=GENERATED))
    assert "Unrated" not in page


def test_a_pdf_keeps_letters_outside_ascii() -> None:
    document = _document([["2026-09-01", "1h", "Møte på Ålesund, café", ""]])
    [page] = _pages(to_pdf(document, generated=GENERATED))
    assert "Møte på Ålesund, café" in page


def test_a_long_report_runs_over_pages_and_repeats_its_headings() -> None:
    rows = [
        [(date(2026, 1, 1) + timedelta(days=day)).isoformat(), "1h", f"Row {day}", ""]
        for day in range(150)
    ]
    pages = _pages(to_pdf(_document(rows), generated=GENERATED))

    assert len(pages) > 2
    for number, page in enumerate(pages, start=1):
        assert f"Page {number} of {len(pages)}" in page
        assert "Made with Cubit, a product of IceCube Solutions" in page
        assert "Note" in page  # the header row starts every page
    assert "Row 0" in pages[0] and "Row 149" in pages[-1]


def test_the_same_report_gives_the_same_file() -> None:
    assert to_pdf(_document(), generated=GENERATED) == to_pdf(_document(), generated=GENERATED)


def test_an_empty_table_says_so() -> None:
    [page] = _pages(to_pdf(_document([]), generated=GENERATED))
    assert "Nothing logged." in page


def test_a_long_note_wraps_inside_its_column() -> None:
    note = "Refactored the invoice export and wrote tests for it " * 6
    widths = _column_widths(
        ["Date", "Time", "Note"], [["2026-09-01", "1h", note]], [False, True, False]
    )

    assert sum(widths) <= CONTENT_WIDTH + 0.01
    lines = _wrap(note, widths[2] - 10)
    assert len(lines) > 1
    assert all(_width(line) <= widths[2] - 10 + 0.01 for line in lines)


def test_the_spare_width_goes_to_the_label_not_a_number() -> None:
    widths = _column_widths(["Project", "Earned (EUR)"], [["Acme", "1.00"]], [False, True])
    assert widths[0] > widths[1]


def test_a_word_wider_than_its_column_is_cut() -> None:
    lines = _wrap("https://example.com/" + "a" * 80, 60)
    assert len(lines) > 1
    assert all(_width(line) <= 60.01 for line in lines)


def test_render_file_gives_text_formats_as_utf8() -> None:
    assert render_file(_document(), "markdown", generated=GENERATED).startswith(b"# September")
    assert render_file(_document(), "pdf", generated=GENERATED).startswith(b"%PDF")


def test_a_project_report_as_a_pdf_lists_its_entries(tmp_path: Path, cli) -> None:
    target = tmp_path / "out" / "acme.pdf"
    result = cli(
        "report", "project", "acme-web", "--entries", "--format", "pdf", "--output", str(target)
    )

    assert result.exit_code == EXIT_OK
    pages = _pages(target.read_bytes())
    assert "Acme website (acme-web)" in pages[0]
    assert "Entries" in pages[0]


def test_a_cli_export_takes_a_title(tmp_path: Path, cli) -> None:
    target = tmp_path / "log.pdf"
    result = cli(
        "report", "month", "--from", "2026-01-01", "--to", "2026-09-30",
        "--title", "Hour log, Acme, January to September",
        "--format", "pdf", "--output", str(target),
    )  # fmt: skip

    assert result.exit_code == EXIT_OK
    assert "Hour log, Acme, January to September" in _pages(target.read_bytes())[0]
    assert "Custom range" not in _pages(target.read_bytes())[0]


def test_with_title_replaces_only_a_real_title() -> None:
    assert with_title(_document(), "Hour log").title == "Hour log"
    assert with_title(_document(), "  ").title == "September 2026"
    assert with_title(_document(), None).title == "September 2026"


def test_a_pdf_is_never_written_to_the_terminal(cli) -> None:
    result = cli("report", "month", "2026-09", "--format", "pdf")
    assert result.exit_code == EXIT_ERROR
    assert "--output" in result.output


def test_downloading_a_month_as_a_pdf(web) -> None:
    response = web.get("/reports/export?view=month&from=2026-09-01&to=2026-09-30&format=pdf")

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert "cubit-month-custom-range.pdf" in response.headers["Content-Disposition"]
    pages = _pages(response.get_data())
    assert "Custom range" in pages[0]
    assert "Acme website" in pages[0]


def test_the_reports_page_offers_a_pdf(web) -> None:
    assert 'value="pdf"' in web.get("/reports/?view=month").get_data(as_text=True)
