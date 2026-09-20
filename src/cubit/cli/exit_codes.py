"""Process exit codes, shared so the CLI and its tests agree on them."""

from __future__ import annotations

#: Everything went fine.
EXIT_OK = 0

#: A user or data error: a short message and a hint were printed (FR-25).
EXIT_ERROR = 1

#: Click's own code for bad usage, e.g. a missing argument.
EXIT_USAGE = 2
