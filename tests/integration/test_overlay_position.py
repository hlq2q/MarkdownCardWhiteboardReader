"""The floating refresh / restore-all strip belongs in the board's bottom-right corner.

T-035: the strip is a child of the *window* but was positioned from the central widget's
size alone, so it sat ``central.x()`` px away from the corner (measured 280 px with the
sidebar open) and stayed behind whenever the board changed size on its own.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from mcwr.interfaces.gui.main_window import OVERLAY_MARGIN, MainWindow


def _settle() -> None:
    app = QApplication.instance()
    assert app is not None
    app.processEvents()


def _gap(window: MainWindow) -> QPoint:
    """Distance from the strip's bottom-right corner to the board's, in px."""
    board = window.view.geometry()
    strip = window.overlay.geometry()
    return QPoint(board.right() - strip.right(), board.bottom() - strip.bottom())


@pytest.fixture
def window() -> MainWindow:
    window = MainWindow(persist=False)
    window.resize(1400, 900)
    window.show()
    _settle()
    return window


def test_the_strip_sits_in_the_board_corner(window: MainWindow) -> None:
    assert _gap(window) == QPoint(OVERLAY_MARGIN, OVERLAY_MARGIN)


def test_the_strip_clears_the_vertical_scroll_bar(window: MainWindow) -> None:
    """The chosen margin must not cover the scroll bar the user still has to drag."""
    assert window.view.verticalScrollBar().sizeHint().width() < OVERLAY_MARGIN


def test_a_window_resize_keeps_the_strip_in_the_corner(window: MainWindow) -> None:
    window.resize(900, 620)
    _settle()
    assert _gap(window) == QPoint(OVERLAY_MARGIN, OVERLAY_MARGIN)


def test_collapsing_the_sidebar_keeps_the_strip_in_the_corner(window: MainWindow) -> None:
    """The board moves to x=0 and grows; the strip must follow it, not stay behind."""
    dock = window._outline_dock
    assert dock is not None
    dock.setVisible(False)
    _settle()
    assert window.view.geometry().x() == 0, "the board should now start at the window edge"
    assert _gap(window) == QPoint(OVERLAY_MARGIN, OVERLAY_MARGIN)


def test_widening_the_sidebar_keeps_the_strip_in_the_corner(window: MainWindow) -> None:
    dock = window._outline_dock
    assert dock is not None
    before = window.view.geometry().x()
    dock.setFixedWidth(dock.width() + 120)
    _settle()
    assert window.view.geometry().x() > before, "the board should have moved right"
    assert _gap(window) == QPoint(OVERLAY_MARGIN, OVERLAY_MARGIN)
