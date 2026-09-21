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


def active_tab(html: str, nav: str = "tabs") -> str:
    """The tab marked ``is-active`` in ``<nav class="...">``, e.g. "Week".

    The page header is a nav of its own, with its own active link, so the one
    being asked about has to be named.
    """
    block = re.search(rf'<nav class="{nav}">(.*?)</nav>', html, re.DOTALL)
    if block is None:
        raise AssertionError(f"no <nav class={nav!r}> in the page")
    match = re.search(r'<a\b[^>]*class="is-active"[^>]*>\s*(.*?)\s*</a>', block.group(1), re.DOTALL)
    if match is None:
        raise AssertionError(f"no tab is marked active in <nav class={nav!r}>")
    return match.group(1)
