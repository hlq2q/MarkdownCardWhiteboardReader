"""Application data and cache locations (FR-7.2, spec §2.5).

Layout state never lives next to the Markdown file: it goes to the app data directory,
while render caches and web assets go to the local cache directory. Nothing here creates
a directory at import time — the store creates what it needs when it first writes.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

APP_DIR_NAME: Final[str] = "MarkdownCardWhiteboardReader"
"""Directory name under ``%APPDATA%`` and ``%LOCALAPPDATA%``."""

HOME_FALLBACK_NAME: Final[str] = ".markdown-card-whiteboard"
"""Hidden directory under the user home, used when the environment variables are unset."""

OVERRIDE_ENV_VAR: Final[str] = "MCWR_APP_DIR"
"""Overrides the data **and** cache base; intended for tests and portable runs."""

LOCAL_OVERRIDE_ENV_VAR: Final[str] = "MCWR_LOCAL_APP_DIR"
"""Overrides the cache base alone; default is ``OVERRIDE_ENV_VAR`` when that is set."""


def app_data_dir() -> Path:
    """Return the directory holding durable state (boards, windows, recent files).

    ``%APPDATA%\\MarkdownCardWhiteboardReader``, or ``~/.markdown-card-whiteboard`` when
    ``APPDATA`` is unset (non-Windows or a stripped environment).
    """
    override = _read_env(OVERRIDE_ENV_VAR)
    if override is not None:
        return override
    roaming = _read_env("APPDATA")
    if roaming is not None:
        return roaming / APP_DIR_NAME
    return Path.home() / HOME_FALLBACK_NAME


def cache_dir() -> Path:
    """Return the directory holding disposable renders and web assets.

    ``%LOCALAPPDATA%\\MarkdownCardWhiteboardReader\\Cache``, or
    ``~/.markdown-card-whiteboard/Cache`` when ``LOCALAPPDATA`` is unset.
    """
    local = _read_env(LOCAL_OVERRIDE_ENV_VAR) or _read_env(OVERRIDE_ENV_VAR)
    if local is not None:
        return local / "Cache"
    local_app_data = _read_env("LOCALAPPDATA")
    if local_app_data is not None:
        return local_app_data / APP_DIR_NAME / "Cache"
    return Path.home() / HOME_FALLBACK_NAME / "Cache"


def assets_dir() -> Path:
    """Return the bundled web assets (KaTeX + Mermaid) shipped inside the package."""
    return Path(__file__).resolve().parents[1] / "assets" / "web"


def _read_env(name: str) -> Path | None:
    """Return an environment variable as a non-empty path, or ``None``."""
    raw = os.environ.get(name, "").strip()
    return Path(raw) if raw else None
