"""MarkdownCardWhiteboardReader (mcwr) — read-only Markdown card whiteboard for Windows."""

from __future__ import annotations

from typing import Final

__version__ = "0.1.0"

PRODUCT_NAME: Final[str] = "MarkdownCardWhiteboardReader"
"""User-facing display name (decision D-026).

Deliberately the same string as ``mcwr.infrastructure.app_paths.APP_DIR_NAME`` ("显示名与
AppName 同步"); a test pins the two together, so they cannot drift apart silently.
"""

__all__ = ["PRODUCT_NAME", "__version__"]
