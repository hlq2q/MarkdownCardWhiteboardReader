"""T-021 acceptance: a TOC line jumps to its heading card (FR-2.4, flow F10).

The click is delivered through the real widget chain — ``QTest.mouseClick`` on the view's
viewport, through ``QGraphicsView``, into ``CardItem.mousePressEvent`` — so the test also
covers the hit test that turns a click into an anchor. The renderer is a stub: nothing here
needs WebEngine.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent  # noqa: F401  # imported for its side-effect typing
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from mcwr.domain.enums import CardKind
from mcwr.interfaces.gui.card_item import CardItem
from mcwr.interfaces.gui.main_window import MainWindow

TOC_DOCUMENT = """[TOC]

# Alpha

text a

## Beta

text b

### Gamma

text c

## Delta

delta body: enough content below Gamma that the board is taller than the viewport, so
"center on the target" is a real scroll rather than a clamp at the end of the board.

### Epsilon

epsilon body.
"""

PLAIN_DOCUMENT = """# Alpha

text a
"""


class StubRenderer:
    last_error = None

    def render(
        self, *, kind: object, source: str, scale: float, theme: str = "light"
    ) -> Path | None:
        del kind, source, scale, theme
        return None


def _write(tmp_path: Path, text: str, name: str = "doc.md") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _item(window: MainWindow, kind: CardKind, title: str = "") -> CardItem:
    for item in window.card_items.values():
        if item.card.kind is kind and (not title or item.card.title == title):
            return item
    raise AssertionError(f"no {kind} card titled {title!r} on the board")


def _find_link(item: CardItem, anchor: str) -> QPointF:
    """The first item-local point inside the body whose text is the wanted link."""
    body = item.body_rect()
    y = int(body.top()) + 2
    while y < int(body.bottom()):
        x = int(body.left()) + 2
        while x < int(min(body.right(), body.left() + 320)):
            point = QPointF(x, y)
            if item.anchor_at(point) == anchor:
                return point
            x += 4
        y += 2
    raise AssertionError(f"the card body has no link to {anchor!r}")


def _open(tmp_path: Path, text: str = TOC_DOCUMENT) -> MainWindow:
    window = MainWindow(persist=False, renderer=StubRenderer())  # type: ignore[arg-type]
    window.show()  # the viewport needs a real geometry for the click mapping
    assert window.open_path(_write(tmp_path, text)) is True
    # 200% keeps the viewport smaller than the board, so ``centerOn`` really has to scroll:
    # at "fit" zoom the whole board fits and Qt clamps the centering (nothing to scroll).
    window.view.set_zoom(200.0)
    QApplication.instance().processEvents()  # type: ignore[union-attr]
    return window


def _click_toc_line(window: MainWindow, toc: CardItem, anchor: str) -> None:
    window.view.centerOn(toc.sceneBoundingRect().center())
    local = _find_link(toc, anchor)
    viewport_point = window.view.mapFromScene(toc.mapToScene(local))
    QTest.mouseClick(window.view.viewport(), Qt.MouseButton.LeftButton, pos=viewport_point)


def _view_center(window: MainWindow) -> QPointF:
    return window.view.mapToScene(window.view.viewport().rect().center())


def test_the_toc_card_lists_every_heading_as_a_link(tmp_path: Path) -> None:
    """The card body is the generated entry list, not the literal ``[TOC]`` marker."""
    window = _open(tmp_path)
    assert [entry.label for entry in window.session.toc] == [
        "Alpha",
        "Beta",
        "Gamma",
        "Delta",
        "Epsilon",
    ]

    toc = _item(window, CardKind.TOC)
    for anchor in ("alpha", "beta", "gamma"):
        _find_link(toc, anchor)  # raises when the line is missing
    assert toc.anchor_at(QPointF(toc.body_rect().left() + 2, toc.body_rect().top() + 1)) == ""


def test_clicking_a_toc_line_centers_the_heading_card(tmp_path: Path) -> None:
    """The acceptance sentence: after the click, the view center is inside the target card."""
    window = _open(tmp_path)
    toc = _item(window, CardKind.TOC)
    gamma = _item(window, CardKind.HEADING, "Gamma")
    epsilon = _item(window, CardKind.HEADING, "Epsilon")
    # Park the view at the far end of the board first, so the jump has to move it.
    window.view.centerOn(epsilon.sceneBoundingRect().center())
    assert not gamma.sceneBoundingRect().contains(_view_center(window))

    position_before = (toc.layout_state.x, toc.layout_state.y)
    _click_toc_line(window, toc, "gamma")

    assert gamma.sceneBoundingRect().contains(_view_center(window)), "the card must be centered"
    assert gamma.isSelected() is True, "F10 also asks for a highlight"
    assert (toc.layout_state.x, toc.layout_state.y) == position_before, (
        "a link click must not drag the card"
    )
    assert "已定位" in window.statusBar().currentMessage()


def test_a_jump_into_a_folded_section_unfolds_the_ancestors_first(tmp_path: Path) -> None:
    """FR-2.4/F10: expand the folded ancestors, then center — and say that it happened."""
    window = _open(tmp_path)
    beta = _item(window, CardKind.HEADING, "Beta")
    gamma = _item(window, CardKind.HEADING, "Gamma")
    window.session.fold(beta.card.card_id)
    QApplication.instance().processEvents()  # type: ignore[union-attr]

    assert window.session.layouts[beta.card.card_id].collapsed is True
    assert gamma.isVisible() is False, "a card inside a folded ancestor is hidden"

    _click_toc_line(window, _item(window, CardKind.TOC), "gamma")

    assert window.session.layouts[beta.card.card_id].collapsed is False
    assert gamma.isVisible() is True
    assert gamma.sceneBoundingRect().contains(_view_center(window))
    assert "已展开 1 层折叠祖先" in window.statusBar().currentMessage()


def test_an_unknown_anchor_reports_instead_of_jumping(tmp_path: Path) -> None:
    window = _open(tmp_path)
    toc = _item(window, CardKind.TOC)
    before = _view_center(window)
    toc.link_clicked.emit(toc, "no-such-heading")
    assert _view_center(window) == before
    assert "未找到" in window.statusBar().currentMessage()


def test_a_document_without_a_toc_marker_has_no_toc_card(tmp_path: Path) -> None:
    """The user's answer (2026-10-12): entries only where ``[TOC]`` is written."""
    window = _open(tmp_path, PLAIN_DOCUMENT)
    assert all(item.card.kind is not CardKind.TOC for item in window.card_items.values())
    assert [entry.label for entry in window.session.toc] == ["Alpha"], (
        "the entries still describe the document; there is simply no card showing them"
    )
