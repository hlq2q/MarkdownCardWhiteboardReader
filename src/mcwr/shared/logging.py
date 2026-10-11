"""Logging setup (spec NFR: key errors must be written to a log, messages stay friendly).

One sink writes to the application's own log directory — never next to the source Markdown
(FR-8) — and a second mirror keeps the CLI usable. The directory can be redirected with
``MCWR_LOG_DIR`` so tests never touch the user's real log file.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Final

from loguru import logger as _logger

_LOG_DIR_ENV: Final[str] = "MCWR_LOG_DIR"
_LOG_NAME: Final[str] = "mcwr.log"
_configured = False


def log_dir() -> Path:
    """Where logs live: ``%LOCALAPPDATA%\\MarkdownCardWhiteboardReader\\logs`` by default."""
    override = os.environ.get(_LOG_DIR_ENV, "").strip()
    if override:
        return Path(override)
    from mcwr.infrastructure.app_paths import cache_dir

    return cache_dir().parent / "logs"


def configure_logging(level: str = "WARNING") -> Path:
    """Install the file sink once and return the log file path."""
    global _configured
    path = log_dir() / _LOG_NAME
    if not _configured:
        path.parent.mkdir(parents=True, exist_ok=True)
        _logger.remove()
        _logger.add(sys.stderr, level=level)
        _logger.add(
            str(path),
            level=level,
            rotation="1 MB",
            retention=3,
            encoding="utf-8",
            enqueue=False,
        )
        _configured = True
    return path


def logger() -> Any:
    """The shared logger (loguru).

    ``Any`` because loguru does not export its ``Logger`` type publicly; call sites just
    use ``logger().warning(...)``. Import this instead of configuring logging elsewhere.
    """
    if not _configured:  # a library user may forget; make logging safe by default
        configure_logging()
    return _logger


def shorten(text: str, limit: int = 40) -> str:
    """Trim a user-facing status message so the status bar stays readable (T-026 item 9)."""
    clean = " ".join(text.split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "…"
