"""Tests for the persisted preferences (T-024, D-030): precedence, merging, no raises.

``MCWR_APP_DIR`` points the whole application data root at a temp directory, so nothing
here touches the user's real ``%APPDATA%`` (the same override the layout store tests use).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcwr.shared.config import (
    DEFAULT_THEME_MODE,
    SETTINGS_NAME,
    THEME_KEY,
    load_settings,
    load_theme_mode,
    save_theme_mode,
    settings_path,
)


@pytest.fixture(autouse=True)
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the application data root and return it (nothing touches %APPDATA%)."""
    monkeypatch.setenv("MCWR_APP_DIR", str(tmp_path))
    return tmp_path


def _write_settings(text: str) -> Path:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_the_settings_file_lives_under_the_application_data_root(data_root: Path) -> None:
    assert settings_path() == data_root / SETTINGS_NAME


def test_the_default_is_follow_the_system(data_root: Path) -> None:
    del data_root
    assert DEFAULT_THEME_MODE == "system"
    assert load_theme_mode() == "system"
    assert load_settings() == {}


def test_a_saved_mode_round_trips(data_root: Path) -> None:
    del data_root
    assert save_theme_mode("dark") is True
    assert load_theme_mode() == "dark"
    assert load_settings()[THEME_KEY] == "dark"


def test_saving_one_preference_keeps_the_others(data_root: Path) -> None:
    del data_root
    path = _write_settings(json.dumps({"future_preference": 7}))
    assert save_theme_mode("light") is True
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored == {"future_preference": 7, THEME_KEY: "light"}


def test_a_malformed_file_falls_back_instead_of_raising(data_root: Path) -> None:
    del data_root
    _write_settings("{ this is not json")
    assert load_settings() == {}
    assert load_theme_mode() == DEFAULT_THEME_MODE


def test_an_unknown_stored_mode_is_ignored(data_root: Path) -> None:
    del data_root
    _write_settings(json.dumps({THEME_KEY: "neon"}))
    assert load_theme_mode() == DEFAULT_THEME_MODE


def test_an_unknown_mode_is_a_programming_error(data_root: Path) -> None:
    del data_root
    with pytest.raises(ValueError, match="neon"):
        save_theme_mode("neon")


def test_no_temp_file_is_left_behind(data_root: Path) -> None:
    del data_root
    assert save_theme_mode("dark") is True
    assert save_theme_mode("light") is True
    leftovers = [p.name for p in settings_path().parent.iterdir() if p.name != SETTINGS_NAME]
    assert leftovers == []
