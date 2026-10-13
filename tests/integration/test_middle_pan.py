"""The middle button pans the board 1:1 and changes nothing else (T-037).

The events are synthesised straight onto the viewport, so the test drives the same handler
the mouse does. The document is tall enough (and zoomed far enough in) that the view has
somewhere to pan in both directions.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QGraphicsView

from mcwr.interfaces.gui.main_window import MainWindow

DOCUMENT = "\n\n".join(f"# Section {index}\n\ntext {index}" for index in range(12))


class StubRenderer:
    last_error = None

    def render(
        self, *, kind: object, source: str, scale: float, theme: str = "light"
    ) -> Path | None:
        del kind, source, scale, theme
        return None


def _settle() -> None:
    app = QApplication.instance()
    assert app is not None
    app.processEvents()


@pytest.fixture
def window(tmp_path: Path) -> MainWindow:
    document = tmp_path / "pan.md"
    document.write_text(DOCUMENT, encoding="utf-8")
    window = MainWindow(persist=False, renderer=StubRenderer())  # type: ignore[arg-type]
    window.resize(900, 620)
    window.show()
    assert window.open_path(document) is True
    window.view.set_zoom(200.0)
    _settle()
    for bar in (window.view.horizontalScrollBar(), window.view.verticalScrollBar()):
        bar.setValue(bar.maximum() // 2)  # mid-range: room to pan either way
    _settle()
    return window


def _send(
    view: QGraphicsView,
    kind: QEvent.Type,
    x: float,
    y: float,
    button: Qt.MouseButton,
    buttons: Qt.MouseButton,
) -> None:
    event = QMouseEvent(
        kind, QPointF(x, y), QPointF(x, y), button, buttons, Qt.KeyboardModifier.NoModifier
    )
    QApplication.sendEvent(view.viewport(), event)


def _drag(
    view: QGraphicsView,
    button: Qt.MouseButton,
    start: tuple[float, float],
    step: tuple[float, float],
    count: int,
) -> None:
    x, y = start
    _send(view, QEvent.Type.MouseButtonPress, x, y, button, button)
    for index in range(1, count + 1):
        _send(
            view,
            QEvent.Type.MouseMove,
            x + step[0] * index,
            y + step[1] * index,
            Qt.MouseButton.NoButton,
            button,
        )
    _send(
        view,
        QEvent.Type.MouseButtonRelease,
        x + step[0] * count,
        y + step[1] * count,
        button,
        Qt.MouseButton.NoButton,
    )


def _bars(window: MainWindow) -> tuple[int, int]:
    view = window.view
    return view.horizontalScrollBar().value(), view.verticalScrollBar().value()


def test_the_board_has_room_to_pan(window: MainWindow) -> None:
    view = window.view
    assert view.horizontalScrollBar().maximum() > 600
    assert view.verticalScrollBar().maximum() > 600


def test_a_middle_drag_moves_the_view_one_to_one(window: MainWindow) -> None:
    before = _bars(window)
    _drag(window.view, Qt.MouseButton.MiddleButton, (400.0, 300.0), (40.0, 30.0), 6)
    _settle()
    assert _bars(window) == (before[0] - 240, before[1] - 180)


def test_the_view_comes_back_after_a_drag_in_the_other_direction(window: MainWindow) -> None:
    before = _bars(window)
    _drag(window.view, Qt.MouseButton.MiddleButton, (400.0, 300.0), (-40.0, -30.0), 3)
    _drag(window.view, Qt.MouseButton.MiddleButton, (400.0, 300.0), (40.0, 30.0), 3)
    _settle()
    assert _bars(window) == before


def test_a_middle_drag_selects_and_moves_nothing(window: MainWindow) -> None:
    scene = window.view.scene()
    assert scene is not None
    scene.clearSelection()
    placed = {card_id: item.scenePos() for card_id, item in window.card_items.items()}
    _drag(window.view, Qt.MouseButton.MiddleButton, (400.0, 300.0), (40.0, 30.0), 6)
    _settle()
    assert scene.selectedItems() == []
    for card_id, item in window.card_items.items():
        assert item.scenePos() == placed[card_id]


def test_the_left_button_keeps_its_rubber_band(window: MainWindow) -> None:
    assert window.view.dragMode() == QGraphicsView.DragMode.RubberBandDrag
    _drag(window.view, Qt.MouseButton.MiddleButton, (400.0, 300.0), (40.0, 30.0), 2)
    assert window.view.dragMode() == QGraphicsView.DragMode.RubberBandDrag


def test_the_cursor_becomes_a_grab_hand_only_while_panning(window: MainWindow) -> None:
    view = window.view
    _send(
        view,
        QEvent.Type.MouseButtonPress,
        400.0,
        300.0,
        Qt.MouseButton.MiddleButton,
        Qt.MouseButton.MiddleButton,
    )
    assert view.viewport().cursor().shape() == Qt.CursorShape.ClosedHandCursor
    _send(
        view,
        QEvent.Type.MouseButtonRelease,
        400.0,
        300.0,
        Qt.MouseButton.MiddleButton,
        Qt.MouseButton.NoButton,
    )
    assert view.viewport().cursor().shape() == Qt.CursorShape.ArrowCursor


def test_the_board_can_pan_sideways_even_when_the_cards_fit(window: MainWindow) -> None:
    """T-040: the scene keeps a screen of margin, so sideways panning never runs out."""
    view = window.view
    view.set_zoom(100.0)
    _settle()
    for bar in (view.horizontalScrollBar(), view.verticalScrollBar()):
        bar.setValue(bar.maximum() // 2)
    _settle()
    assert view.horizontalScrollBar().maximum() > 600, "no room to pan sideways"
    before = _bars(window)
    _drag(view, Qt.MouseButton.MiddleButton, (400.0, 300.0), (-40.0, -30.0), 6)
    _settle()
    assert _bars(window) == (before[0] + 240, before[1] + 180)
