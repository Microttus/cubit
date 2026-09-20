"""What every command needs: which data folder, and the storage over it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import typer

from cubit.core import Config, CubitError, Storage, resolve_data_dir


@dataclass
class AppContext:
    """Shared state put on the Typer context by the root callback."""

    storage: Storage

    @property
    def data_dir(self) -> Path:
        return self.storage.data_dir

    def require_folder(self) -> Storage:
        """The storage, refusing to guess if the folder was never created."""
        if not self.storage.exists:
            raise CubitError(
                f"No cubit data folder at {self.data_dir}.",
                hint="Create one with 'cubit init', or point at another with --data-dir.",
            )
        return self.storage

    def config(self) -> Config:
        return self.storage.load_config()


def build_context(data_dir: str | None) -> AppContext:
    """Resolve the data folder: --data-dir, CUBIT_DATA_DIR, then the default (FR-26)."""
    return AppContext(storage=Storage(resolve_data_dir(data_dir)))


def get_context(ctx: typer.Context) -> AppContext:
    """The AppContext the root callback put in place."""
    if not isinstance(ctx.obj, AppContext):  # pragma: no cover - defensive
        ctx.obj = build_context(None)
    return ctx.obj
