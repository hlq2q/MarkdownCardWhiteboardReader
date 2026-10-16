"""Right-drag marquee, moving a selection as one group, edge-first snapping (T-051/D-052).

Real mouse events throughout: the marquee is driven with the right button, the group move with the
left button on a card that is part of the selection.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QGraphicsView

from mcwr.interfaces.gui.main_window import MainWindow

HEADER_HEIGHT = 34.0

DOCUMENT = """# G

text g

## P

text p

### A

text a

### B

text b

# H

text h
"""


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
    document = tmp_path / "selection.md"
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


def _selected(window: MainWindow) -> set[str]:
    document = window.session.document
    assert document is not None
    titles = {card_id: card.title for card_id, card in document.tree.cards.items()}
    return {
        titles[item.card.card_id]
        for item in window.view.scene().selectedItems()
        if hasattr(item, "card")
    }


def _marquee_over(window: MainWindow, titles: list[str]) -> None:
    """Right-drag a band around the given cards (with a margin) to select them."""
    view = window.view
    rect = QRectF()
    for title in titles:
        rect = rect.united(window.card_items[_id(window, title)].sceneBoundingRect())
    rect = rect.adjusted(-10.0, -10.0, 10.0, 10.0)
    start = view.mapFromScene(rect.topLeft())
    end = view.mapFromScene(rect.bottomRight())
    _send(
        view,
        QEvent.Type.MouseButtonPress,
        float(start.x()),
        float(start.y()),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
    )
    for step in range(1, 4):
        _send(
            view,
            QEvent.Type.MouseMove,
            start.x() + (end.x() - start.x()) * step / 3.0,
            start.y() + (end.y() - start.y()) * step / 3.0,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.RightButton,
        )
    _send(
        view,
        QEvent.Type.MouseButtonRelease,
        float(end.x()),
        float(end.y()),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.NoButton,
    )
    _settle()


def _drag_body_by(window: MainWindow, title: str, dx: float, dy: float) -> None:
    """Drag a card's body by a scene delta (converted through the view scale)."""
    view = window.view
    item = window.card_items[_id(window, title)]
    scale = view.transform().m11()
    origin = view.mapFromScene(
        item.scenePos() + QPointF(item.card_width / 2.0, HEADER_HEIGHT + 20.0)
    )
    end = QPointF(origin.x() + dx * scale, origin.y() + dy * scale)
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
            origin.x() + (end.x() - origin.x()) * step / 5.0,
            origin.y() + (end.y() - origin.y()) * step / 5.0,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
        )
    _send(
        view,
        QEvent.Type.MouseButtonRelease,
        float(end.x()),
        float(end.y()),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
    )
    _settle()


def test_a_right_drag_selects_only_the_cards_that_can_move(window: MainWindow) -> None:
    """The marquee takes free cards; a frozen child inside the band stays out of it (D-050)."""
    window.session.detach(_id(window, "A"))
    window.session.detach(_id(window, "B"))
    _settle()
    _marquee_over(window, ["A", "B", "P"])
    assert _selected(window) == {"A", "B"}


def test_a_left_click_on_empty_space_gives_the_menu_back(window: MainWindow) -> None:
    """The flow the user described: clear the selection, then the right button is a menu again."""
    window.session.detach(_id(window, "A"))
    window.session.detach(_id(window, "B"))
    _settle()
    _marquee_over(window, ["A", "B"])
    assert window.view.suppresses_context_menu() is True

    view = window.view
    corner = view.mapFromScene(QRectF(0.0, 0.0, 1.0, 1.0).topLeft())
    _send(
        view,
        QEvent.Type.MouseButtonPress,
        float(corner.x()),
        float(corner.y()),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
    )
    _send(
        view,
        QEvent.Type.MouseButtonRelease,
        float(corner.x()),
        float(corner.y()),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
    )
    _settle()
    assert window.view.suppresses_context_menu() is False


def test_a_right_click_without_a_drag_still_opens_the_menu(window: MainWindow) -> None:
    """A right press that never moved is a click, not a marquee."""
    view = window.view
    item = window.card_items[_id(window, "G")]
    point = view.mapFromScene(item.scenePos() + QPointF(item.card_width / 2.0, 10.0))
    _send(
        view,
        QEvent.Type.MouseButtonPress,
        float(point.x()),
        float(point.y()),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
    )
    assert window.view.suppresses_context_menu() is False
    _send(
        view,
        QEvent.Type.MouseButtonRelease,
        float(point.x()),
        float(point.y()),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.NoButton,
    )
    _settle()


def test_dragging_one_selected_card_moves_the_whole_selection(window: MainWindow) -> None:
    a_id = _id(window, "A")
    b_id = _id(window, "B")
    window.session.detach(a_id)
    window.session.detach(b_id)
    _settle()
    window.action_snap.setChecked(False)  # exact deltas, no snapping
    _marquee_over(window, ["A", "B"])
    assert _selected(window) == {"A", "B"}
    before_a = (window.session.layouts[a_id].x, window.session.layouts[a_id].y)
    before_b = (window.session.layouts[b_id].x, window.session.layouts[b_id].y)

    _drag_body_by(window, "A", 70.0, 45.0)

    after_a = (window.session.layouts[a_id].x, window.session.layouts[a_id].y)
    after_b = (window.session.layouts[b_id].x, window.session.layouts[b_id].y)
    moved_a = (after_a[0] - before_a[0], after_a[1] - before_a[1])
    moved_b = (after_b[0] - before_b[0], after_b[1] - before_b[1])
    assert moved_a == pytest.approx((70.0, 45.0), abs=1.5)
    assert moved_b == pytest.approx(moved_a, abs=0.01), "the group moves as one"


def test_a_dropped_card_settles_on_a_neighbours_edge(window: MainWindow) -> None:
    """Edges win over the grid: a drop just right of a card lands exactly on its edge (D-052)."""
    a_id = _id(window, "A")
    b_id = _id(window, "B")
    window.session.detach(a_id)
    _settle()
    b_layout = window.session.layouts[b_id]
    start = window.session.layouts[a_id]
    # Put A 1 px to the right of B's right edge and keep its y: with the tighter indent three
    # edges (B.right, the former parent's right, the other root's right) sit within the 12 px
    # tolerance, and the nearest wins -- 1 px makes B's edge unambiguously the nearest (D-052).
    window.session.move_card(a_id, b_layout.x + b_layout.width + 1.0, start.y, snap=True)
    _settle()
    assert window.session.layouts[a_id].x == pytest.approx(b_layout.x + b_layout.width, abs=0.5), (
        "the edge snap must line the two cards up exactly"
    )
