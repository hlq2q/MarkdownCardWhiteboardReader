"""Durable user preferences that are not part of a board snapshot (T-024, D-030).

One preference lives here today: the theme mode. It is stored in the application data
directory — never next to the source Markdown (FR-8) — as a small JSON file written
atomically, and it is *merged*, so a future preference cannot be lost by writing this one.

Every read degrades instead of raising: an unreadable or malformed settings file must never
block a window from opening (acceptance 10). A write reports failure by returning ``False``;
an unknown mode is a programming error and raises.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from mcwr.infrastructure._atomic import write_text_atomic

SETTINGS_NAME: Final[str] = "settings.json"
THEME_KEY: Final[str] = "theme_mode"
THEME_MODES: Final[tuple[str, ...]] = ("system", "light", "dark")
DEFAULT_THEME_MODE: Final[str] = "system"
"""D-030: follow the Windows app theme until the user picks light or dark explicitly."""


def settings_path() -> Path:
    """``%APPDATA%\\MarkdownCardWhiteboardReader\\settings.json`` (tests redirect the root)."""
    from mcwr.infrastructure.app_paths import app_data_dir

    return app_data_dir() / SETTINGS_NAME


def load_settings() -> dict[str, object]:
    """The stored settings, or an empty mapping when the file is missing or unusable."""
    try:
        raw = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def load_theme_mode(default: str = DEFAULT_THEME_MODE) -> str:
    """The stored theme mode, or ``default`` when it is absent or not a known mode."""
    stored = load_settings().get(THEME_KEY)
    if isinstance(stored, str) and stored in THEME_MODES:
        return stored
    return default


def save_theme_mode(mode: str) -> bool:
    """Persist ``mode`` atomically; ``False`` means "not saved", never an exception."""
    if mode not in THEME_MODES:
        raise ValueError(f"unknown theme mode: {mode!r}")
    settings = load_settings()
    settings[THEME_KEY] = mode
    try:
        text = json.dumps(settings, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        write_text_atomic(settings_path(), text)
    except OSError:
        return False
    return True
