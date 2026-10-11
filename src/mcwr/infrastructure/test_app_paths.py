"""Tests for the app data and cache locations (FR-7.2, spec §2.5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcwr.infrastructure.app_paths import (
    APP_DIR_NAME,
    HOME_FALLBACK_NAME,
    LOCAL_OVERRIDE_ENV_VAR,
    OVERRIDE_ENV_VAR,
    app_data_dir,
    cache_dir,
)

_ENV_VARS = ("APPDATA", "LOCALAPPDATA", OVERRIDE_ENV_VAR, LOCAL_OVERRIDE_ENV_VAR)


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test may read the real %APPDATA% or inherit another test's override."""
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_app_data_dir_follows_roaming_app_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert app_data_dir() == tmp_path / APP_DIR_NAME


def test_cache_dir_follows_local_app_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert cache_dir() == tmp_path / APP_DIR_NAME / "Cache"


def test_falls_back_to_the_home_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("H:/home/tester")))
    assert app_data_dir() == Path("H:/home/tester") / HOME_FALLBACK_NAME
    assert cache_dir() == Path("H:/home/tester") / HOME_FALLBACK_NAME / "Cache"


def test_override_moves_both_directories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPDATA", "R:/real")
    monkeypatch.setenv("LOCALAPPDATA", "R:/real-local")
    monkeypatch.setenv(OVERRIDE_ENV_VAR, str(tmp_path))
    assert app_data_dir() == tmp_path
    assert cache_dir() == tmp_path / "Cache"


def test_local_override_wins_for_the_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OVERRIDE_ENV_VAR, str(tmp_path / "data"))
    monkeypatch.setenv(LOCAL_OVERRIDE_ENV_VAR, str(tmp_path / "local"))
    assert app_data_dir() == tmp_path / "data"
    assert cache_dir() == tmp_path / "local" / "Cache"


def test_blank_environment_values_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPDATA", "   ")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("H:/home/tester")))
    assert app_data_dir() == Path("H:/home/tester") / HOME_FALLBACK_NAME


def test_reading_the_paths_creates_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OVERRIDE_ENV_VAR, str(tmp_path / "app"))
    app_data_dir()
    cache_dir()
    assert list(tmp_path.rglob("*")) == []  # directories appear only on the first write
