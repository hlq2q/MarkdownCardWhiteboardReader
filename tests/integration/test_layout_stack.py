"""The column stays tight, and a card inside its parent stays where it is (T-036/41/43).

Document shape: ``# G`` holds ``## P``, ``P`` holds ``### A`` and ``### B``, and ``# H`` follows
``G`` at the same level. Heights come from real font metrics, so the assertions are written as
relationships rather than absolute pixel values; the detach -> restore round trip can be compared
exactly.

Since T-043 an attached card cannot be dragged at all, so the manual-move scenarios these tests
used to drive through ``session.move_card`` are gone: the overlap repair and the box hug are
covered at unit level in ``layout_board/test_stack.py``, and what is checked here is the
structural behaviour plus the freeze itself (driven by real mouse events on the viewport).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QGraphicsView

from mcwr.interfaces.gui.main_window import MainWindow

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
    document = tmp_path / "stack.md"
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


def _box(window: MainWindow, card_id: str) -> tuple[float, float, float, float]:
    layout = window.session.layouts[card_id]
    return layout.x, layout.y, layout.width, layout.height


def _rect(window: MainWindow, title: str) -> tuple[float, float, float, float]:
    return _box(window, _id(window, title))


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


def _drag_card(
    window: MainWindow,
    title: str,
    *,
    offset_y: float = HEADER_HEIGHT + 20.0,
    distance: float = 120.0,
) -> None:
    """Drag the card straight down with real mouse events, the way a user would.

    ``offset_y`` chooses where the card is grabbed: its body by default, or its title bar
    (the case that used to move the card behind it, E-027).
    """
    view = window.view
    item = window.card_items[_id(window, title)]
    start = view.mapFromScene(item.scenePos() + QPointF(item.card_width / 2.0, offset_y))
    steps = 6
    _send(
        view,
        QEvent.Type.MouseButtonPress,
        float(start.x()),
        float(start.y()),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
    )
    for step in range(1, steps + 1):
        _send(
            view,
            QEvent.Type.MouseMove,
            float(start.x()),
            float(start.y()) + distance * step / steps,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
        )
    _send(
        view,
        QEvent.Type.MouseButtonRelease,
        float(start.x()),
        float(start.y()) + distance,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
    )
    _settle()


def test_detaching_a_card_tightens_the_whole_ancestor_chain(window: MainWindow) -> None:
    before = {title: _rect(window, title) for title in ("P", "G", "H")}
    window.session.detach(_id(window, "A"))
    shrink = _rect(window, "P")[3] - before["P"][3]
    assert shrink < 0, "the parent must shrink when a child leaves"
    assert _rect(window, "G")[3] == pytest.approx(before["G"][3] + shrink)
    assert _rect(window, "H")[1] == pytest.approx(before["H"][1] + shrink)


def test_restoring_a_card_puts_the_whole_arrangement_back(window: MainWindow) -> None:
    titles = ("P", "G", "H", "A", "B")
    before = {title: _rect(window, title) for title in titles}
    window.session.detach(_id(window, "A"))
    assert _rect(window, "G")[3] != pytest.approx(before["G"][3])
    window.session.restore(_id(window, "A"))
    for title in titles:
        assert _rect(window, title) == pytest.approx(before[title])


def test_a_child_inside_its_parent_cannot_be_dragged(window: MainWindow) -> None:
    """T-043: its relative position is frozen, so a drag leaves it exactly where it was."""
    before = _rect(window, "B")
    item = window.card_items[_id(window, "B")]
    _drag_card_down(window, "B")
    assert _rect(window, "B") == before
    assert item.scenePos() == QPointF(before[0], before[1])
    # ... and the domain refuses the move as well, not only the item flag (T-043).
    window.session.move_card(_id(window, "B"), before[0] + 50.0, before[1] + 50.0)
    assert _rect(window, "B") == before


def test_a_free_card_can_be_dragged_and_its_subtree_follows(window: MainWindow) -> None:
    """The other half of the rule: a card outside its parent still moves, children included."""
    window.session.detach(_id(window, "G"))
    _settle()
    before_g = _rect(window, "G")
    before_p = _rect(window, "P")
    _drag_card_down(window, "G")
    after_g = _rect(window, "G")
    after_p = _rect(window, "P")
    assert after_g[1] > before_g[1], "a free card must still be draggable"
    assert after_p[1] - before_p[1] == pytest.approx(after_g[1] - before_g[1])
    assert after_p[0] - before_p[0] == pytest.approx(after_g[0] - before_g[0])


def test_a_child_never_sits_on_its_parents_own_content(window: MainWindow) -> None:
    """The freeze keeps children in the slot the layout gave them, below the parent's text."""
    document = window.session.document
    assert document is not None
    for card_id, card in document.tree.cards.items():
        if card.parent_id is None:
            continue
        parent = document.tree.cards[card.parent_id]
        if parent.is_big_section:
            continue  # a separator card has no header of its own
        child_y = _box(window, card_id)[1]
        parent_y = _box(window, parent.card_id)[1]
        assert child_y >= parent_y + HEADER_HEIGHT


def test_every_item_points_at_the_current_layout_object(window: MainWindow) -> None:
    """E-026: a re-layout replaces CardLayout objects, so the item must follow the new one.

    The boundary clamp reads ``detached`` from the object the item holds; a stale reference
    silently applies the wrong rule (a card that was just detached stayed clamped, a restored one
    could leave its parent).
    """
    window.session.detach(_id(window, "A"))
    window.session.restore(_id(window, "A"))
    for card_id, item in window.card_items.items():
        assert item.layout_state is window.session.layouts[card_id]


def test_a_drag_from_the_title_bar_grabs_that_card(window: MainWindow) -> None:
    """E-027: Qt's delivery skips a card whose title bar is pressed; the view takes over."""
    document = window.session.document
    assert document is not None
    root_id = document.tree.root_ids[0]
    g_id = _id(window, "G")
    window.session.detach(g_id)
    _settle()
    before_card = _box(window, g_id)
    before_root = _box(window, root_id)
    _drag_card(window, "G", offset_y=10.0)
    assert _box(window, g_id)[1] > before_card[1], "the grabbed card must be the one that moves"
    assert _box(window, root_id) == before_root, "the card behind it must stay put"


def test_a_title_bar_press_on_a_frozen_child_moves_nothing(window: MainWindow) -> None:
    """A frozen child consumes its own title-bar press, so the card behind it stays put."""
    document = window.session.document
    assert document is not None
    root_id = document.tree.root_ids[0]
    before_root = _box(window, root_id)
    before_child = _box(window, _id(window, "B"))
    _drag_card(window, "B", offset_y=10.0)
    assert _box(window, root_id) == before_root
    assert _box(window, _id(window, "B")) == before_child


def test_a_drag_from_the_title_bar_grabs_that_card(window: MainWindow) -> None:
    """E-027: Qt's delivery skips a card whose title bar is pressed; the view takes over."""
    document = window.session.document
    assert document is not None
    root_id = document.tree.root_ids[0]
    g_id = _id(window, "G")
    window.session.detach(g_id)
    _settle()
    before_card = _box(window, g_id)
    before_root = _box(window, root_id)
    _drag_card(window, "G", offset_y=10.0)
    assert _box(window, g_id)[1] > before_card[1], "the grabbed card must be the one that moves"
    assert _box(window, root_id) == before_root, "the card behind it must stay put"


def test_a_title_bar_press_on_a_frozen_child_moves_nothing(window: MainWindow) -> None:
    """A frozen child consumes its own title-bar press, so the card behind it stays put."""
    document = window.session.document
    assert document is not None
    root_id = document.tree.root_ids[0]
    before_root = _box(window, root_id)
    before_child = _box(window, _id(window, "B"))
    _drag_card(window, "B", offset_y=10.0)
    assert _box(window, root_id) == before_root
    assert _box(window, _id(window, "B")) == before_child
