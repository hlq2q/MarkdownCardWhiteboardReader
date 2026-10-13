"""A mouse drag in a card's body selects its text, and Ctrl+C copies it (T-063)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from mcwr.interfaces.gui.main_window import MainWindow
from mcwr.interfaces.gui.theme import HEADER_HEIGHT, PADDING

DOCUMENT = """# Alpha

the quick brown fox jumps over the lazy dog

# Beta

another body line here
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


def _card(window: MainWindow, title: str) -> object:
    document = window.session.document
    assert document is not None
    for card_id, card in document.tree.cards.items():
        if card.title == title:
            return window.card_items[card_id]
    raise KeyError(title)


def _point(window: MainWindow, item: object, dx: float, dy: float) -> QPointF:
    return QPointF(
        *window.view.mapFromScene(
            item.scenePos() + QPointF(dx, dy)  # type: ignore[attr-defined]
        ).toTuple()
    )


def _drag(window: MainWindow, start: QPointF, end: QPointF) -> None:
    for kind, point, buttons in (
        (QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton),
        (QEvent.Type.MouseMove, end, Qt.MouseButton.LeftButton),
        (QEvent.Type.MouseButtonRelease, end, Qt.MouseButton.NoButton),
    ):
        QApplication.sendEvent(
            window.view.viewport(),
            QMouseEvent(
                kind,
                point,
                point,
                Qt.MouseButton.LeftButton,
                buttons,
                Qt.KeyboardModifier.NoModifier,
            ),
        )
    _settle()


def test_dragging_in_the_body_selects_text_and_does_not_move_the_card(
    window: MainWindow,
) -> None:
    item = _card(window, "Alpha")
    before = item.scenePos()  # type: ignore[attr-defined]
    body_y = HEADER_HEIGHT + PADDING + 6.0

    _drag(window, _point(window, item, 12.0, body_y), _point(window, item, 260.0, body_y))

    assert item.has_selection() is True  # type: ignore[attr-defined]
    assert "quick" in item.selected_text()  # type: ignore[attr-defined]
    assert item.scenePos() == before, "the body press must not move the card any more"  # type: ignore[attr-defined]


def test_ctrl_c_copies_the_selection_to_the_clipboard(window: MainWindow) -> None:
    item = _card(window, "Alpha")
    body_y = HEADER_HEIGHT + PADDING + 6.0
    _drag(window, _point(window, item, 12.0, body_y), _point(window, item, 260.0, body_y))

    QApplication.sendEvent(
        window.view,
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier),
    )
    _settle()

    copied = QApplication.clipboard().text()
    assert copied == item.selected_text()  # type: ignore[attr-defined]
    assert "quick" in copied


def test_the_title_bar_is_still_the_drag_handle(window: MainWindow) -> None:
    item = _card(window, "Alpha")
    before = item.scenePos()  # type: ignore[attr-defined]

    _drag(
        window, _point(window, item, 12.0, HEADER_HEIGHT / 2.0), _point(window, item, 12.0, 200.0)
    )

    assert item.scenePos() != before, "a title-bar drag still moves the card (E-027)"
    assert item.has_selection() is False  # type: ignore[attr-defined]


def test_a_new_press_on_another_card_drops_the_old_selection(window: MainWindow) -> None:
    first = _card(window, "Alpha")
    body_y = HEADER_HEIGHT + PADDING + 6.0
    _drag(window, _point(window, first, 12.0, body_y), _point(window, first, 260.0, body_y))
    assert first.has_selection() is True  # type: ignore[attr-defined]

    second = _card(window, "Beta")
    _drag(window, _point(window, second, 12.0, body_y), _point(window, second, 200.0, body_y))

    assert first.has_selection() is False  # type: ignore[attr-defined]
    assert second.has_selection() is True  # type: ignore[attr-defined]
