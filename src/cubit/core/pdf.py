"""A report as a PDF, with the Cubit logo on it (FR-80).

The PDF is written by hand rather than through a library: a report is text
and ruled tables, which takes a few hundred lines, and keeps Cubit free of a
heavy dependency (AGENT.md). The two fonts are ones every PDF reader has built
in, and the logo is drawn as vector shapes from the same geometry as
``cubit-mark.svg``, so nothing is embedded and the file stays small.

Like the rest of :mod:`cubit.core.export`, this is pure: a document and a date
in, bytes out. The date is passed in so the same report always gives the same
file.
"""

from __future__ import annotations

import re
import zlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from cubit.core.pdf_metrics import BOLD, REGULAR

if TYPE_CHECKING:
    from cubit.core.export import Document, Table

#: A4, in points.
PAGE_WIDTH = 595.28
PAGE_HEIGHT = 841.89
MARGIN = 48.0
FOOTER_HEIGHT = 40.0
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN

#: Table text.
SIZE = 8.5
LEADING = 11.0
CELL_PAD_X = 5.0
CELL_PAD_Y = 3.5

#: The line on every page.
FOOTER = "Made with Cubit, a product of IceCube Solutions"

#: Print colours, taken from the logo so the page matches the app.
INK = (0.10, 0.12, 0.14)
MUTED = (0.37, 0.42, 0.46)
ACCENT = (0.0, 0.525, 0.659)  # #0086a8, the cube's right face
HEADER_FILL = (0.90, 0.976, 0.992)
STRIPE_FILL = (0.965, 0.973, 0.98)
RULE = (0.81, 0.85, 0.87)

#: A cell that holds a number, a time or a duration, and is right-aligned.
NUMERIC = re.compile(r"^[\d\s.,:%()hm+-]*\d[\d\s.,:%()hm+-]*$")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def to_pdf(document: Document, *, generated: date) -> bytes:
    """The document as a PDF: a header with the logo, its tables, a footer."""
    writer = _Writer()
    writer.header(document, generated)
    for table in document.tables:
        writer.table(table)
    return writer.finish(document.title)


# ------------------------------------------------------------------ layout


@dataclass
class _Writer:
    """Lays a document out page by page, top to bottom."""

    pages: list[list[bytes]] = field(default_factory=list)
    y: float = 0.0

    def __post_init__(self) -> None:
        self._new_page()

    @property
    def ops(self) -> list[bytes]:
        return self.pages[-1]

    def _new_page(self) -> None:
        self.pages.append([])
        self.y = PAGE_HEIGHT - MARGIN

    def _room_for(self, height: float) -> None:
        """Start a new page unless ``height`` fits above the footer."""
        if self.y - height < MARGIN + FOOTER_HEIGHT:
            self._new_page()

    def header(self, document: Document, generated: date) -> None:
        logo = 30.0
        top = self.y
        self.ops.append(_logo(MARGIN, top - logo, logo))
        self.ops.append(_text(MARGIN + logo + 8, top - 21, "Cubit", bold=True, size=18))
        stamp = f"Generated {generated.isoformat()}"
        self.ops.append(
            _text(
                PAGE_WIDTH - MARGIN - _width(stamp, size=8.5),
                top - 19,
                stamp,
                size=8.5,
                color=MUTED,
            )
        )
        self.y = top - logo - 10
        self.ops.append(_rule(MARGIN, self.y, PAGE_WIDTH - MARGIN, ACCENT, 1.2))

        self.y -= 28
        for line in _wrap(document.title, CONTENT_WIDTH, bold=True, size=16):
            self.ops.append(_text(MARGIN, self.y, line, bold=True, size=16))
            self.y -= 20
        for line in _wrap(document.subtitle, CONTENT_WIDTH, size=10):
            self.ops.append(_text(MARGIN, self.y, line, size=10, color=MUTED))
            self.y -= 13
        self.y -= 8

    def table(self, table: Table) -> None:
        columns, rows = _visible(table)
        right = [_is_numeric(rows, index) for index in range(len(columns))]
        widths = _column_widths(columns, rows, right)
        header = [
            _wrap(name, width - 2 * CELL_PAD_X, bold=True)
            for name, width in zip(columns, widths, strict=True)
        ]
        header_height = _row_height(header)
        bodies = [
            [_wrap(cell, width - 2 * CELL_PAD_X) for cell, width in zip(row, widths, strict=True)]
            for row in rows
        ]

        # The title never ends a page on its own: it keeps its header and a row.
        first = _row_height(bodies[0]) if bodies else LEADING + 2 * CELL_PAD_Y
        self._room_for(26 + header_height + first)
        self.y -= 14
        self.ops.append(_text(MARGIN, self.y, table.title, bold=True, size=11, color=ACCENT))
        self.y -= 8
        self._header_row(header, widths, right, header_height)

        if not bodies:
            baseline = self.y - CELL_PAD_Y - SIZE
            self.ops.append(_text(MARGIN + CELL_PAD_X, baseline, "Nothing logged.", color=MUTED))
            self.y -= LEADING + 2 * CELL_PAD_Y
        for index, cells in enumerate(bodies):
            height = _row_height(cells)
            if self.y - height < MARGIN + FOOTER_HEIGHT:
                self._new_page()
                self._header_row(header, widths, right, header_height)
            if index % 2:
                self.ops.append(_box(MARGIN, self.y - height, CONTENT_WIDTH, height, STRIPE_FILL))
            self._cells(cells, widths, right, bold=False)
            self.y -= height
        self.ops.append(_rule(MARGIN, self.y, PAGE_WIDTH - MARGIN, RULE, 0.6))
        self.y -= 10

    def _header_row(
        self, cells: list[list[str]], widths: list[float], right: list[bool], height: float
    ) -> None:
        self.ops.append(_box(MARGIN, self.y - height, CONTENT_WIDTH, height, HEADER_FILL))
        self._cells(cells, widths, right, bold=True)
        self.y -= height
        self.ops.append(_rule(MARGIN, self.y, PAGE_WIDTH - MARGIN, ACCENT, 0.8))

    def _cells(
        self, cells: list[list[str]], widths: list[float], right: list[bool], *, bold: bool
    ) -> None:
        x = MARGIN
        for lines, width, align_right in zip(cells, widths, right, strict=True):
            baseline = self.y - CELL_PAD_Y - SIZE
            for line in lines:
                left = x + CELL_PAD_X
                if align_right:
                    left = x + width - CELL_PAD_X - _width(line, bold=bold)
                self.ops.append(_text(left, baseline, line, bold=bold))
                baseline -= LEADING
            x += width

    def finish(self, title: str) -> bytes:
        total = len(self.pages)
        for number, ops in enumerate(self.pages, start=1):
            ops.extend(_footer(number, total))
        return _assemble([b"\n".join(ops) for ops in self.pages], title)


def _footer(number: int, total: int) -> list[bytes]:
    y = MARGIN - 6
    page = f"Page {number} of {total}"
    return [
        _rule(MARGIN, y + 14, PAGE_WIDTH - MARGIN, RULE, 0.6),
        _logo(MARGIN, y - 3, 11),
        _text(MARGIN + 15, y, FOOTER, size=8, color=MUTED),
        _text(PAGE_WIDTH - MARGIN - _width(page, size=8), y, page, size=8, color=MUTED),
    ]


def _visible(table: Table) -> tuple[list[str], list[list[str]]]:
    """The table without columns that are empty in every row, like Unrated."""
    keep = [
        index
        for index in range(len(table.columns))
        if not table.rows or any(row[index] for row in table.rows)
    ]
    return (
        [table.columns[index] for index in keep],
        [[row[index] for index in keep] for row in table.rows],
    )


def _column_widths(
    columns: Sequence[str], rows: Sequence[Sequence[str]], numeric: Sequence[bool]
) -> list[float]:
    """Share the page width between the columns.

    Every column asks for its widest cell. When they all fit, the widest text
    column (a label or a note, never a number) takes the slack so the table
    spans the page. When they do not, the space
    is shared out narrowest first, so short columns like times keep their
    width and the long ones (a note, a project name) wrap.
    """
    natural = [
        max([_width(name, bold=True)] + [_width(row[index]) for row in rows]) + 2 * CELL_PAD_X
        for index, name in enumerate(columns)
    ]
    if sum(natural) <= CONTENT_WIDTH:
        widths = list(natural)
        text = [index for index in range(len(natural)) if not numeric[index]] or range(len(natural))
        widest = max(text, key=lambda index: natural[index])
        widths[widest] += CONTENT_WIDTH - sum(natural)
        return widths

    widths = [0.0] * len(natural)
    remaining = CONTENT_WIDTH
    order = sorted(range(len(natural)), key=lambda index: natural[index])
    for position, index in enumerate(order):
        widths[index] = min(natural[index], remaining / (len(order) - position))
        remaining -= widths[index]
    return widths


def _is_numeric(rows: Sequence[Sequence[str]], index: int) -> bool:
    cells = [row[index] for row in rows if row[index]]
    return bool(cells) and all(NUMERIC.match(cell) and not ISO_DATE.match(cell) for cell in cells)


def _row_height(cells: Sequence[Sequence[str]]) -> float:
    return max(len(lines) for lines in cells) * LEADING + 2 * CELL_PAD_Y


# -------------------------------------------------------------------- text


def _clean(text: str) -> str:
    return CONTROL.sub(" ", text)


def _encode(text: str) -> bytes:
    """Windows-1252, the encoding the built-in fonts use; anything else is '?'."""
    return _clean(text).encode("cp1252", errors="replace")


def _width(text: str, *, bold: bool = False, size: float = SIZE) -> float:
    table = BOLD if bold else REGULAR
    return sum(table[code - 32] for code in _encode(text)) * size / 1000


def _wrap(text: str, width: float, *, bold: bool = False, size: float = SIZE) -> list[str]:
    """Break ``text`` into lines that fit ``width``, between words where possible."""
    # A column is exactly as wide as its widest cell, so rounding must not wrap it.
    width += 0.01
    lines: list[str] = []
    current = ""
    for word in _clean(text).split():
        candidate = f"{current} {word}" if current else word
        if _width(candidate, bold=bold, size=size) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        # A word wider than the column (a URL, say) is cut where it has to be.
        while _width(word, bold=bold, size=size) > width and len(word) > 1:
            cut = len(word) - 1
            while cut > 1 and _width(word[:cut], bold=bold, size=size) > width:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        current = word
    lines.append(current)
    return lines


def _escape(data: bytes) -> bytes:
    return data.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


# ---------------------------------------------------------------- drawing


def _rgb(color: tuple[float, float, float]) -> bytes:
    return " ".join(_num(part) for part in color).encode()


def _num(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".") or "0"


def _text(
    x: float,
    y: float,
    text: str,
    *,
    bold: bool = False,
    size: float = SIZE,
    color: tuple[float, float, float] = INK,
) -> bytes:
    font = b"/F2" if bold else b"/F1"
    return (
        b"BT "
        + _rgb(color)
        + b" rg "
        + font
        + b" "
        + _num(size).encode()
        + b" Tf "
        + f"{_num(x)} {_num(y)}".encode()
        + b" Td ("
        + _escape(_encode(text))
        + b") Tj ET"
    )


def _rule(x1: float, y: float, x2: float, color: tuple[float, float, float], width: float) -> bytes:
    return (
        _rgb(color)
        + b" RG "
        + _num(width).encode()
        + b" w "
        + f"{_num(x1)} {_num(y)} m {_num(x2)} {_num(y)} l S".encode()
    )


def _box(x: float, y: float, w: float, h: float, color: tuple[float, float, float]) -> bytes:
    return _rgb(color) + f" rg {_num(x)} {_num(y)} {_num(w)} {_num(h)} re f".encode()


#: The cube from cubit-mark.svg, in its own 64-unit box with y pointing down.
_FACES = (
    ((32, 4, 56, 18, 32, 32, 8, 18), (0.608, 0.937, 1.0)),  # #9befff, top
    ((8, 18, 32, 32, 32, 60, 8, 46), (0.0, 0.831, 1.0)),  # #00d4ff, left
    ((32, 32, 56, 18, 56, 46, 32, 60), (0.0, 0.525, 0.659)),  # #0086a8, right
)
_OUTLINE = (32, 4, 56, 18, 56, 46, 32, 60, 8, 46, 8, 18)
_OUTLINE_COLOR = (0.0, 0.278, 0.361)  # #00475c
_HANDS_COLOR = (0.016, 0.133, 0.173)  # #04222c


def _logo(x: float, y: float, size: float) -> bytes:
    """The Cubit mark, ``size`` points square, its lower-left corner at x, y."""
    scale = size / 64
    ops = [f"q {_num(scale)} 0 0 {_num(-scale)} {_num(x)} {_num(y + size)} cm".encode()]
    for points, color in _FACES:
        ops.append(_rgb(color) + b" rg " + _path(points) + b" f")
    ops.append(_rgb(_OUTLINE_COLOR) + b" RG 1.5 w 1 j " + _path(_OUTLINE) + b" s")
    # The top face is a clock at 3:00, with a dot where the hands meet.
    ops.append(_rgb(_HANDS_COLOR) + b" RG 1.8 w 1 J 32 18 m 32 9 l 32 18 m 41.6 18 l S")
    ops.append(_rgb(_HANDS_COLOR) + b" rg " + _circle(32, 18, 1.6) + b" f")
    ops.append(b"Q")
    return b" ".join(ops)


def _path(points: Sequence[float]) -> bytes:
    pairs = [points[index : index + 2] for index in range(0, len(points), 2)]
    first, *rest = pairs
    parts = [f"{first[0]} {first[1]} m"] + [f"{px} {py} l" for px, py in rest]
    return (" ".join(parts) + " h").encode()


def _circle(cx: float, cy: float, r: float) -> bytes:
    k = 0.5523 * r
    return (
        f"{_num(cx + r)} {_num(cy)} m "
        f"{_num(cx + r)} {_num(cy + k)} {_num(cx + k)} {_num(cy + r)} {_num(cx)} {_num(cy + r)} c "
        f"{_num(cx - k)} {_num(cy + r)} {_num(cx - r)} {_num(cy + k)} {_num(cx - r)} {_num(cy)} c "
        f"{_num(cx - r)} {_num(cy - k)} {_num(cx - k)} {_num(cy - r)} {_num(cx)} {_num(cy - r)} c "
        f"{_num(cx + k)} {_num(cy - r)} {_num(cx + r)} {_num(cy - k)} {_num(cx + r)} {_num(cy)} c"
    ).encode()


# ---------------------------------------------------------------- the file


def _assemble(contents: Sequence[bytes], title: str) -> bytes:
    """Wrap the page contents in the objects a PDF reader expects."""
    page_count = len(contents)
    # 1 catalog, 2 page tree, 3 and 4 fonts, 5 info, then a page and its stream each.
    first_page = 6
    page_ids = [first_page + 2 * index for index in range(page_count)]

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids ["
        + b" ".join(f"{page_id} 0 R".encode() for page_id in page_ids)
        + f"] /Count {page_count} >>".encode(),
        _font(b"Helvetica"),
        _font(b"Helvetica-Bold"),
        b"<< /Title " + _info_string(title) + b" /Producer (Cubit, IceCube Solutions) >>",
    ]
    for page_id, content in zip(page_ids, contents, strict=True):
        objects.append(
            b"<< /Type /Page /Parent 2 0 R "
            + f"/MediaBox [0 0 {_num(PAGE_WIDTH)} {_num(PAGE_HEIGHT)}] ".encode()
            + b"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            + f"/Contents {page_id + 1} 0 R >>".encode()
        )
        packed = zlib.compress(content)
        objects.append(
            f"<< /Length {len(packed)} /Filter /FlateDecode >>\nstream\n".encode()
            + packed
            + b"\nendstream"
        )

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info 5 0 R >>\n".encode()
    out += f"startxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def _font(name: bytes) -> bytes:
    return b"<< /Type /Font /Subtype /Type1 /BaseFont /" + name + b" /Encoding /WinAnsiEncoding >>"


def _info_string(text: str) -> bytes:
    """A metadata string as UTF-16, so any title survives."""
    return b"<FEFF" + _clean(text).encode("utf-16-be").hex().upper().encode() + b">"
