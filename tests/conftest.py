"""Shared test configuration.

Qt needs a platform plugin; the offscreen plugin keeps GUI tests headless and is set
before PySide6 is imported anywhere.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def qapp() -> None:
    """One QApplication for the whole test session (Qt allows only one)."""
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
