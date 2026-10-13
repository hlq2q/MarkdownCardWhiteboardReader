"""Ctrl + wheel scales a free card's subtree; Ctrl + right double-click gives the size back (T-057).

Only a card the user pulled out of its parent carries a factor of its own: an attached card gets its
width from the column and a parentless card is the board's frame. Everything below a scaled card
inherits the factor, so the arrangement inside it is untouched.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication

from mcwr.interfaces.gui.main_window import MainWindow
from mcwr.interfaces.gui.theme import HEADER_HEIGHT

DOCUMENT = """# G

text g

## P

text p

### A

text a

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
    document = tmp_path / "scaling.md"
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


def _body_point(window: MainWindow, title: str) -> QPointF:
    item = window.card_items[_id(window, title)]
    return QPointF(
        *window.view.mapFromScene(
            item.scenePos() + QPointF(item.card_width / 2.0, HEADER_HEIGHT + 20.0)
        ).toTuple()
    )


def _wheel(window: MainWindow, point: QPointF, *, control: bool) -> None:
    modifiers = Qt.KeyboardModifier.ControlModifier if control else Qt.KeyboardModifier.NoModifier
    event = QWheelEvent(
        point,
        point,
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        modifiers,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(window.view.viewport(), event)
    _settle()


def _ctrl_right_double_click(window: MainWindow, point: QPointF) -> None:
    event = QMouseEvent(
        QEvent.Type.MouseButtonDblClick,
        point,
        point,
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.ControlModifier,
    )
    QApplication.sendEvent(window.view.viewport(), event)
    _settle()


def test_ctrl_wheel_scales_a_free_card_and_everything_inside_it(window: MainWindow) -> None:
    g_id = _id(window, "G")
    window.session.detach(g_id)
    _settle()
    p_id, a_id = _id(window, "P"), _id(window, "A")
    before = {card_id: window.session.layouts[card_id].width for card_id in (g_id, p_id, a_id)}
    assert window.card_items[g_id].effective_scale == 1.0

    _wheel(window, _body_point(window, "G"), control=True)

    assert window.session.layouts[g_id].scale > 1.0
    for card_id, width in before.items():
        assert window.session.layouts[card_id].width > width, "the subtree scales with the card"
    assert window.card_items[g_id].effective_scale > 1.0
    assert window.card_items[p_id].effective_scale == pytest.approx(
        window.card_items[g_id].effective_scale
    ), "a child inherits the factor instead of carrying its own"


def test_a_card_that_was_not_pulled_out_cannot_be_scaled(window: MainWindow) -> None:
    g_id = _id(window, "G")
    before = window.session.layouts[g_id].width

    _wheel(window, _body_point(window, "G"), control=True)

    assert window.session.layouts[g_id].scale == 1.0
    assert window.session.layouts[g_id].width == before
    assert "free card" in window.statusBar().currentMessage()


def test_ctrl_right_double_click_restores_the_natural_size(window: MainWindow) -> None:
    g_id = _id(window, "G")
    window.session.detach(g_id)
    _settle()
    before = window.session.layouts[g_id].width
    point = _body_point(window, "G")
    _wheel(window, point, control=True)
    assert window.session.layouts[g_id].scale > 1.0

    _ctrl_right_double_click(window, point)

    assert window.session.layouts[g_id].scale == 1.0
    assert window.session.layouts[g_id].width == pytest.approx(before, abs=1.0)
    assert window.card_items[g_id].effective_scale == 1.0
    assert window.view.suppresses_context_menu() is True, "the gesture is not a context-menu click"


def test_returning_a_scaled_card_to_its_parent_resets_the_size(window: MainWindow) -> None:
    """The mistake the user asked to avoid: a scaled card must not go back into the column."""
    g_id = _id(window, "G")
    window.session.detach(g_id)
    _settle()
    _wheel(window, _body_point(window, "G"), control=True)
    assert window.session.layouts[g_id].scale > 1.0

    window.session.restore(g_id)
    _settle()

    assert window.session.layouts[g_id].scale == 1.0
    assert window.session.layouts[g_id].detached is False


def test_a_plain_wheel_still_zooms_the_canvas(window: MainWindow) -> None:
    before = window.view.transform().m11()

    _wheel(window, _body_point(window, "G"), control=False)

    assert window.view.transform().m11() > before, "Ctrl is what changes the card, not the wheel"
