"""Category normalization, ranking and registration (FR-43 to FR-48, FR-52).

A category is a short reusable label for the work inside one project, stored as
a lowercase slug without the ``#``. The ``#`` is display and input sugar only;
normalization happens here and nowhere else.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from collections.abc import Iterable, Sequence
from datetime import date, time
from typing import TYPE_CHECKING, Protocol

from cubit.core.errors import CategoryError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from cubit.core.models import Entry, Project

#: A stored category: lowercase letters, digits and hyphens, at most 40 long.
CATEGORY_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

MAX_CATEGORY_LENGTH = 40

#: Characters that do not survive unicode decomposition on their own.
_TRANSLITERATIONS = {"ø": "o", "æ": "ae", "ß": "ss", "đ": "d", "ð": "d", "þ": "th", "ł": "l"}


def normalize_category(name: str) -> str:
    """Normalize a category name to its stored slug (FR-48).

    ``Project Management``, ``project management`` and ``#project-management``
    all become ``project-management``. Raises :class:`CategoryError` if nothing
    usable is left or the slug is longer than 40 characters.
    """
    raw = (name or "").strip()
    if not raw:
        raise CategoryError("Empty category name.")

    text = raw.lstrip("#").strip().lower()
    text = "".join(_TRANSLITERATIONS.get(char, char) for char in text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")

    if not slug:
        raise CategoryError(
            f"Category {name!r} has no letters or digits.",
            hint="Use a name like software-coding.",
        )
    if len(slug) > MAX_CATEGORY_LENGTH:
        raise CategoryError(
            f"Category {slug!r} is longer than {MAX_CATEGORY_LENGTH} characters.",
            hint="Use a shorter name.",
        )
    return slug


def normalize_optional_category(name: str | None) -> str | None:
    """Normalize a category that may be missing. Blank means uncategorized."""
    if name is None or not name.strip():
        return None
    return normalize_category(name)


def display_category(name: str | None) -> str:
    """Render a stored slug for humans: ``#software-coding``, or a dash."""
    return f"#{name}" if name else "-"


def is_normalized(name: str) -> bool:
    """True if ``name`` is already a valid stored slug."""
    return bool(name) and len(name) <= MAX_CATEGORY_LENGTH and bool(CATEGORY_PATTERN.match(name))


class _Logged(Protocol):
    """The part of an entry that ranking needs."""

    date: date
    start: time | None
    category: str | None


def rank_categories(
    registered: Iterable[str],
    entries: Iterable[_Logged] = (),
) -> list[str]:
    """Order a project's categories for suggestion (FR-46).

    Used categories come first, most recently used first, ties broken by how
    often they were used and then by name. Registered but unused categories
    follow, alphabetically. ``entries`` should already be narrowed to the
    project being logged against (FR-47); a category that appears in the
    entries but is not registered is still suggested.
    """
    registered_slugs = list(dict.fromkeys(registered))
    last_used: dict[str, tuple[date, time]] = {}
    counts: dict[str, int] = {}

    for entry in entries:
        slug = entry.category
        if not slug:
            continue
        counts[slug] = counts.get(slug, 0) + 1
        moment = (entry.date, entry.start or time(0, 0))
        if slug not in last_used or moment > last_used[slug]:
            last_used[slug] = moment

    used = sorted(
        counts,
        key=lambda slug: (last_used[slug], counts[slug], _reverse_name(slug)),
        reverse=True,
    )
    unused = sorted(slug for slug in registered_slugs if slug not in counts)
    return used + unused


def suggest_categories(
    project: Project,
    entries: Iterable[Entry],
    limit: int | None = None,
) -> list[str]:
    """Ranked suggestions for one project, optionally capped at ``limit``.

    Entries for other projects are ignored, so callers can pass everything they
    have loaded (FR-47).
    """
    own = [entry for entry in entries if entry.project_id == project.id]
    ranked = rank_categories(project.categories, own)
    return ranked[:limit] if limit is not None else ranked


def closest_category(name: str, registered: Sequence[str], cutoff: float = 0.8) -> str | None:
    """Return a registered category close to ``name``, for the typo guard (FR-52).

    ``None`` when nothing is close enough or the name is already registered.
    """
    slug = normalize_category(name)
    if slug in registered:
        return None
    matches = difflib.get_close_matches(slug, list(registered), n=1, cutoff=cutoff)
    return matches[0] if matches else None


def _reverse_name(slug: str) -> tuple[int, ...]:
    """Sort key that makes a reversed sort put names in alphabetical order."""
    return tuple(-ord(char) for char in slug)
