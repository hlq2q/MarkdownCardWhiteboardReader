"""Right-button behaviour the user reported: the card menu, and no surprise scrolling.

Both cases drive real mouse events, because the bugs lived exactly in the event plumbing: Qt skips
a card when the point is in its title bar (E-027), and a right double click used to scroll the view.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QContextMenuEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QGraphicsView

from mcwr.interfaces.gui.card_item import CardItem
from mcwr.interfaces.gui.main_window import MainWindow
from mcwr.interfaces.gui.theme import HEADER_HEIGHT  # single source (T-077)

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

    def render(self, *, kind, source, scale, theme: str = "light"):  # noqa: ANN001, ANN201
        return None


def _settle() -> None:
    for _ in range(3):
        QApplication.processEvents()


@pytest.fixture
def window(tmp_path: Path) -> MainWindow:
    document = tmp_path / "context.md"
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
    raise AssertionError(f"no card titled {title!r}")


def _title_bar_point(window: MainWindow, title: str) -> QPointF:
    """A viewport point inside the card's *title bar* -- where a user right-clicks a card."""
    view = window.view
    item = window.card_items[_id(window, title)]
    scene_point = item.scenePos() + QPointF(item.card_width / 2.0, HEADER_HEIGHT / 2.0)
    return QPointF(view.mapFromScene(scene_point))


def _send(view: QGraphicsView, kind: QEvent.Type, point: QPointF, button, buttons) -> None:
    event = QMouseEvent(
        kind,
        point,
        view.viewport().mapToGlobal(point),
        button,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(view.viewport(), event)
    if kind is QEvent.Type.MouseButtonPress:
        view.mousePressEvent(event)
    elif kind is QEvent.Type.MouseButtonRelease:
        view.mouseReleaseEvent(event)
    elif kind is QEvent.Type.MouseButtonDblClick:
        view.mouseDoubleClickEvent(event)
    QApplication.processEvents()


def test_a_right_click_on_the_title_bar_offers_the_card_menu(
    window: MainWindow, monkeypatch
) -> None:
    """The window owns the context-menu event, and the card must be found in its title bar.

    Two faults lived here: nothing accepted the event at all (the view uses ``DefaultContextMenu``,
    so the old ``customContextMenuRequested`` connection could never fire and no menu appeared), and
    the lookup used ``QGraphicsView.itemAt``, which Qt skips for a point in a title bar (E-027).
    This drives the real event, in *window* coordinates -- the path the user actually takes.
    """
    view = window.view
    item = window.card_items[_id(window, "G")]
    scene_point = item.scenePos() + QPointF(item.card_width / 2.0, HEADER_HEIGHT / 2.0)
    viewport_point = view.mapFromScene(scene_point)
    window_point = view.viewport().mapTo(window, viewport_point)

    shown: list[list[str]] = []

    def _capture(menu):  # noqa: ANN001, ANN202
        shown.append([action.text() for action in menu.actions()])

    monkeypatch.setattr(MainWindow, "_exec_menu", lambda self, menu, position: _capture(menu))

    event = QContextMenuEvent(
        QContextMenuEvent.Reason.Mouse,
        window_point,
        view.viewport().mapToGlobal(viewport_point),
    )
    QApplication.sendEvent(window, event)
    _settle()

    assert shown, "no context menu was shown at all"
    assert any("自由卡片" in text for text in shown[0]), (
        "the card's own menu section is missing -- the event never reached the window, or the "
        "lookup missed the title bar (E-027)"
    )


def test_a_right_click_on_the_title_bar_finds_the_card(window: MainWindow) -> None:
    """The white-box half: the lookup must see a card the point is inside, title bar or not."""
    point = _title_bar_point(window, "G").toPoint()

    found = window._card_at(point)

    assert isinstance(found, CardItem), "no card found: the title-bar blind spot is back"
    assert found.card.title == "G"


def test_a_right_double_click_does_not_scroll_the_board(window: MainWindow) -> None:
    """A quick second right click must not move the view: that looked like the card jumping."""
    view = window.view
    point = _title_bar_point(window, "G")
    bar = view.horizontalScrollBar()
    bar.setValue(bar.maximum())  # the card is off-centre now, so a centreOn would scroll
    before = (bar.value(), view.verticalScrollBar().value())

    _send(
        view,
        QEvent.Type.MouseButtonDblClick,
        point,
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
    )

    assert (bar.value(), view.verticalScrollBar().value()) == before, (
        "a right double click scrolled the board -- that is the card appearing to jump to the edge"
    )
