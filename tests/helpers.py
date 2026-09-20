"""Small helpers shared by the test modules."""

from __future__ import annotations

import re


def text_of(response) -> str:
    """A response body as text, for readable assertions."""
    return response.get_data(as_text=True)


def forms_in(html: str) -> list[str]:
    """Every <form> element in a page, as raw HTML."""
    return re.findall(r"<form\b.*?</form>", html, re.DOTALL)


def row_for(html: str, needle: str) -> str:
    """The table row containing ``needle``, with its tags stripped."""
    for row in re.findall(r"<tr\b.*?</tr>", html, re.DOTALL):
        if needle in row:
            return " ".join(re.sub(r"<[^>]+>", " ", row).split())
    raise AssertionError(f"no row containing {needle!r}")
