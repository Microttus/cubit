"""The optional macOS menu bar app (FR-63 to FR-75).

A third front end on the same core. Importing this package does not import
rumps: :mod:`cubit.menubar.model` is pure and runs anywhere, and only
:mod:`cubit.menubar.app` needs macOS.
"""

from cubit.menubar.model import MenuModel, build_menu, format_hm

__all__ = ["MenuModel", "build_menu", "format_hm"]
