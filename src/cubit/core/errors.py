"""Error types for cubit.core.

Every error raised out of core is a :class:`CubitError`, so the CLI and the web
app can turn it into a short message instead of a traceback (FR-25).
Errors that come from a data file always name the file, and the row or line
where the problem is (FR-38).
"""

from __future__ import annotations

from pathlib import Path


class CubitError(Exception):
    """Base class for all errors core raises on purpose."""

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def __str__(self) -> str:
        return self.message


class DataFileError(CubitError):
    """A data file could not be read or is invalid.

    The message always starts with the file, and with the row or line when we
    know it, so the user can go and fix it by hand (FR-38).
    """

    def __init__(
        self,
        path: Path | str,
        message: str,
        *,
        row: int | None = None,
        line: int | None = None,
        hint: str | None = None,
    ) -> None:
        self.path = Path(path)
        self.row = row
        self.line = line
        where = str(self.path)
        if row is not None:
            where = f"{where} row {row}"
        elif line is not None:
            where = f"{where} line {line}"
        super().__init__(f"{where}: {message}", hint=hint)


class TimerError(CubitError):
    """The requested timer operation does not fit the current timer state."""


class ProjectError(CubitError):
    """The requested project does not exist, or cannot be used as asked."""


class DurationError(CubitError):
    """A duration could not be parsed (FR-27)."""


class CategoryError(CubitError):
    """A category name is not usable (FR-48)."""
