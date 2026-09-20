"""Flask web app. Thin layer over :mod:`cubit.core`."""

from cubit.web.app import DEFAULT_HOST, DEFAULT_PORT, create_app

__all__ = ["DEFAULT_HOST", "DEFAULT_PORT", "create_app"]
