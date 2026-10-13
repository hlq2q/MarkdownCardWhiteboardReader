"""Grid snapping: a free card dropped near a line lands on it (T-048/D-051).

The snap is decided per axis with a 12 px tolerance and applied when the drag ends, so the card
follows the mouse freely and only the last few pixels are pulled. The painted grid and the snap
step must be the same pitch, otherwise snapping would visibly miss the lines drawn on screen.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QGraphicsView

from mcwr.application.features.layout_board.grid import GRID_STEP
from mcwr.interfaces.gui.main_window import MainWindow
from mcwr.interfaces.gui.theme import GRID_STEP as PAINTED_GRID_STEP

DOCUMENT = "# G\n\ntext g\n\n## P\n\ntext p\n"

HEADER_HEIGHT = 34.0


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
    document = tmp_path / "snap.md"
    document.write_text(DOCUMENT, encoding="utf-8")
    window = MainWindow(persist=False, renderer=StubRenderer())  # type: ignore[arg-type]
    window.resize(1200, 900)
    window.show()
    assert window.open_path(document) is True
    _settle()
    return window


def _id(window: MainWindow, title: str) -> str:
    document = window.session.document
    assert document is not None
    for card_id, card in document.tree.cards.items():
        if card.title == title:
            return card_id
    raise KeyError(title)


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


def _drag_body_to(window: MainWindow, card_id: str, target: tuple[float, float]) -> None:
    """Drag the card by its body so the item ends up at ``target`` (scene units)."""
    view = window.view
    item = window.card_items[card_id]
    start = item.scenePos()
    scale = view.transform().m11()
    origin = view.mapFromScene(start + QPointF(item.card_width / 2.0, HEADER_HEIGHT / 2.0))
    end_x = origin.x() + (target[0] - start.x()) * scale
    end_y = origin.y() + (target[1] - start.y()) * scale
    _send(
        view,
        QEvent.Type.MouseButtonPress,
        float(origin.x()),
        float(origin.y()),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
    )
    for step in range(1, 6):
        _send(
            view,
            QEvent.Type.MouseMove,
            origin.x() + (end_x - origin.x()) * step / 5.0,
            origin.y() + (end_y - origin.y()) * step / 5.0,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
        )
    _send(
        view,
        QEvent.Type.MouseButtonRelease,
        end_x,
        end_y,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
    )
    _settle()


def test_the_snap_step_is_the_painted_grid() -> None:
    """Snapping to another pitch than the drawn grid would look broken on screen."""
    assert GRID_STEP == PAINTED_GRID_STEP


def test_the_switch_is_on_by_default(window: MainWindow) -> None:
    assert window.action_snap.isCheckable()
    assert window.action_snap.isChecked()


def test_a_drop_near_a_line_lands_on_it_and_leaves_the_other_axis(window: MainWindow) -> None:
    card_id = _id(window, "G")
    window.session.detach(card_id)
    _settle()
    start = window.session.layouts[card_id]
    # Two lines away from the card itself and 8 px above the line: no neighbour edge is within
    # reach there, so the grid is what settles x (an edge would win otherwise, D-052).
    line = math.floor(start.x / GRID_STEP) * GRID_STEP + 2 * GRID_STEP
    target_x = line + 8.0
    target_y = math.floor((start.y + 200.0) / GRID_STEP) * GRID_STEP + 20.0  # 20 px off: y stays
    _drag_body_to(window, card_id, (target_x, target_y))
    layout = window.session.layouts[card_id]
    assert layout.x == pytest.approx(line, abs=0.5)
    # the free axis keeps where it was dropped; the view maps through integer viewport pixels,
    # so allow a couple of them of slack (a snap would be off by 20, not by 0.5)
    assert layout.y == pytest.approx(target_y, abs=2.0)


def test_turning_the_switch_off_keeps_the_dropped_position(window: MainWindow) -> None:
    card_id = _id(window, "G")
    window.session.detach(card_id)
    _settle()
    window.action_snap.setChecked(False)
    start = window.session.layouts[card_id]
    line = math.floor(start.x / GRID_STEP) * GRID_STEP + GRID_STEP
    target_x = line + 5.0
    _drag_body_to(window, card_id, (target_x, start.y + 20.0))
    layout = window.session.layouts[card_id]
    assert layout.x == pytest.approx(target_x, abs=2.0)
