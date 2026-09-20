"""Pydantic models for everything cubit stores.

The models mirror the file formats in REQUIREMENTS.md section 4 one to one.
Money is :class:`~decimal.Decimal`, durations are whole minutes, and dates are
local ``datetime.date``; only the timer's ``started_at`` is timezone-aware.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cubit.core.categories import normalize_category, normalize_optional_category

#: Project ids and similar slugs: lowercase letters, digits and hyphens.
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

#: Entry ids are six hex characters (REQUIREMENTS 4.1).
ENTRY_ID_PATTERN = re.compile(r"^[0-9a-f]{6}$")

Slug = Annotated[str, Field(min_length=1, max_length=64)]


class ProjectStatus(StrEnum):
    """Whether a project still shows up in pickers and default lists (FR-13)."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Rate(_Model):
    """One step of a project's hourly-rate history (FR-14)."""

    valid_from: date
    rate: Decimal = Field(ge=0)

    @field_validator("rate", mode="before")
    @classmethod
    def _as_decimal(cls, value: object) -> object:
        # Go through str so a YAML float never brings its binary error along.
        return Decimal(str(value)) if isinstance(value, float) else value


class Project(_Model):
    """A client project entries are logged against (FR-11)."""

    id: Slug
    name: str = Field(min_length=1)
    client: str = ""
    status: ProjectStatus = ProjectStatus.ACTIVE
    categories: list[str] = Field(default_factory=list)
    budget_hours: Decimal | None = Field(default=None, gt=0)
    rates: list[Rate] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _valid_slug(cls, value: str) -> str:
        if not SLUG_PATTERN.match(value):
            raise ValueError(
                f"project id {value!r} must be a lowercase slug, "
                "using only letters, digits and hyphens"
            )
        return value

    @field_validator("budget_hours", mode="before")
    @classmethod
    def _budget_as_decimal(cls, value: object) -> object:
        return Decimal(str(value)) if isinstance(value, float) else value

    @field_validator("categories")
    @classmethod
    def _normalized_categories(cls, value: list[str]) -> list[str]:
        # Normalize and drop duplicates, keeping the hand-written order (FR-44).
        return list(dict.fromkeys(normalize_category(name) for name in value))

    @field_validator("rates")
    @classmethod
    def _sorted_rates(cls, value: list[Rate]) -> list[Rate]:
        seen = {rate.valid_from for rate in value}
        if len(seen) != len(value):
            raise ValueError("two rates share the same valid_from date")
        return sorted(value, key=lambda rate: rate.valid_from)

    @property
    def is_active(self) -> bool:
        return self.status is ProjectStatus.ACTIVE

    @property
    def budget_minutes(self) -> int | None:
        """The hour budget as whole minutes, or ``None`` when unset."""
        if self.budget_hours is None:
            return None
        return int((self.budget_hours * 60).to_integral_value(rounding="ROUND_HALF_UP"))

    def with_category(self, name: str) -> Project:
        """Return a copy with ``name`` registered, appended at the end (FR-45)."""
        slug = normalize_category(name)
        if slug in self.categories:
            return self
        return self.model_copy(update={"categories": [*self.categories, slug]})


class Entry(_Model):
    """One logged stretch of work (REQUIREMENTS 4.1)."""

    id: str
    date: date
    start: time | None = None
    end: time | None = None
    duration_minutes: int = Field(ge=1)
    project_id: Slug
    category: str | None = None
    note: str = ""

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not ENTRY_ID_PATTERN.match(value):
            raise ValueError(f"entry id {value!r} must be six hex characters")
        return value

    @field_validator("category", mode="before")
    @classmethod
    def _normalized_category(cls, value: object) -> object:
        return normalize_optional_category(value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def _times_come_in_pairs(self) -> Entry:
        if (self.start is None) != (self.end is None):
            raise ValueError("start and end must both be set or both be blank")
        return self

    @property
    def sort_key(self) -> tuple[date, time, str]:
        """Stable write order: date, start, id (FR-42)."""
        return (self.date, self.start or time(0, 0), self.id)


class Config(_Model):
    """Settings from ``config.yaml`` (REQUIREMENTS 4.3)."""

    currency: str = "EUR"
    week_starts_on: Literal["monday", "sunday"] = "monday"
    budget_warning_percent: int = Field(default=80, ge=1, le=100)
    prompt_for_category: bool = True
    theme: Literal["dark", "light", "auto"] = "dark"

    @field_validator("week_starts_on", "theme", mode="before")
    @classmethod
    def _lowercase(cls, value: object) -> object:
        return value.lower() if isinstance(value, str) else value


class TimerState(_Model):
    """The running timer in ``.state/timer.json`` (REQUIREMENTS 4.4).

    ``started_at`` is timezone-aware so elapsed time stays right across a DST
    change; stored entries use local ``HH:MM``.
    """

    project_id: Slug
    started_at: datetime
    category: str | None = None
    note: str = ""

    @field_validator("started_at")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("started_at must include a UTC offset")
        return value

    @field_validator("category", mode="before")
    @classmethod
    def _normalized_category(cls, value: object) -> object:
        return normalize_optional_category(value) if isinstance(value, str) else value
