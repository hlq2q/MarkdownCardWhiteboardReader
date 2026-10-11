"""Shared test configuration.

Qt needs a platform plugin; the offscreen plugin keeps GUI tests headless and is set
before PySide6 is imported anywhere.

The second fixture is a correctness guard, not a convenience: PySide6 **swallows**
exceptions raised inside a slot (it prints them through ``sys.excepthook`` and carries
on), so without this hook a broken GUI callback shows up as a passing test. Any
captured exception fails the test that triggered it.
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path
from types import TracebackType

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def qapp() -> None:
    """One QApplication for the whole test session (Qt allows only one)."""
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def qt_slot_errors_fail_the_test(monkeypatch: pytest.MonkeyPatch) -> object:
    """Turn exceptions swallowed inside Qt slots into test failures."""
    captured: list[tuple[type[BaseException], BaseException, TracebackType | None]] = []

    def hook(
        exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None
    ) -> None:
        captured.append((exc_type, exc, tb))
        traceback.print_exception(exc_type, exc, tb)

    monkeypatch.setattr(sys, "excepthook", hook)
    yield
    if captured:
        exc_type, exc, tb = captured[0]
        summary = "".join(traceback.format_exception(exc_type, exc, tb))
        raise AssertionError(
            f"{len(captured)} exception(s) were raised inside a Qt slot:\n{summary}"
        )
