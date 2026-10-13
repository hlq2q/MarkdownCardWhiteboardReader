"""T-019 acceptance: the toolbar search box finds cards and centers them.

Semantics come straight from the user's answers: the match is case-sensitive and looks at a
card's whole own text (not only its title). The box is driven through its own signal, so the
test exercises the same path the Enter key takes.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication, QLineEdit

from mcwr.interfaces.gui.main_window import MainWindow

DOCUMENT = """[TOC]

# Alpha

alpha body with the shared token

## Beta

beta body with the shared token

### Gamma

gamma body text

## Delta

delta body text: enough words below the headings that centering is a real scroll instead of
a clamp at the end of the board, and tall enough to survive a 200% zoom.

### Epsilon

epsilon body text.

# Zeta

zeta body text: this trailing card gives the board enough height that centering the cards
above it is a real scroll rather than a clamp at the end of the board.

Filler paragraph one, deliberately long enough to make the last card tall.

Filler paragraph two, same reason: the viewport is a few hundred scene units high at 200%
zoom, so the board must extend at least half of that below the last heading.

Filler paragraph three, closing the document.
"""

CENTER_TOLERANCE_PX = 2.0


class StubRenderer:
    last_error = None

    def render(
        self, *, kind: object, source: str, scale: float, theme: str = "light"
    ) -> Path | None:
        del kind, source, scale, theme
        return None


def _open(tmp_path: Path, text: str = DOCUMENT) -> MainWindow:
    document = tmp_path / "search.md"
    document.write_text(text, encoding="utf-8")
    window = MainWindow(persist=False, renderer=StubRenderer())  # type: ignore[arg-type]
    window.show()
    assert window.open_path(document) is True
    window.view.set_zoom(200.0)
    QApplication.instance().processEvents()  # type: ignore[union-attr]
    return window


def _box(window: MainWindow) -> QLineEdit:
    box = window._search_box
    assert box is not None
    return box


def _search(window: MainWindow, query: str) -> None:
    """Type into the box and press Enter the way the user does."""
    _box(window).setText(query)
    _box(window).returnPressed.emit()


def _center_of(window: MainWindow, title: str) -> object:
    document = window.session.document
    assert document is not None
    for card_id, item in window.card_items.items():
        if item.card.title == title and document.tree.cards[card_id].kind.value == "heading":
            return item
    raise AssertionError(f"no heading card titled {title!r}")


def _view_center(window: MainWindow) -> object:
    return window.view.mapToScene(window.view.viewport().rect().center())


def _assert_centered(window: MainWindow, item: object) -> None:
    center, expected = _view_center(window), item.sceneBoundingRect().center()
    assert abs(center.x() - expected.x()) <= CENTER_TOLERANCE_PX, (center, expected)
    assert abs(center.y() - expected.y()) <= CENTER_TOLERANCE_PX, (center, expected)


def test_the_toolbar_has_a_search_box(tmp_path: Path) -> None:
    window = _open(tmp_path)
    box = _box(window)
    assert box.isVisible()
    assert "搜索" in box.placeholderText()
    assert box in window.findChildren(QLineEdit)


def test_a_title_hit_is_centered_and_selected(tmp_path: Path) -> None:
    window = _open(tmp_path)
    gamma = _center_of(window, "Gamma")
    far = _center_of(window, "Epsilon")
    window.view.centerOn(far.sceneBoundingRect().center())
    assert not gamma.sceneBoundingRect().contains(_view_center(window))

    _search(window, "Gamma")

    _assert_centered(window, gamma)
    assert gamma.isSelected() is True
    message = window.statusBar().currentMessage()
    assert "1/1" in message and "已定位" in message


def test_body_text_matches_too(tmp_path: Path) -> None:
    window = _open(tmp_path)
    _search(window, "epsilon body text")
    _assert_centered(window, _center_of(window, "Epsilon"))
    assert "1/1" in window.statusBar().currentMessage()


def test_the_match_is_case_sensitive(tmp_path: Path) -> None:
    """``GAMMA`` appears in no casing-correct place; ``gamma`` matches the body text only."""
    window = _open(tmp_path)
    before = _view_center(window)
    _search(window, "GAMMA")
    assert "未找到" in window.statusBar().currentMessage()
    assert _view_center(window) == before, "a miss must not move the view"
    assert not any(item.isSelected() for item in window.card_items.values())

    _search(window, "gamma")
    assert "1/1" in window.statusBar().currentMessage(), "lower-case body text must match"
    _assert_centered(window, _center_of(window, "Gamma"))


def test_enter_again_walks_through_the_hits_and_wraps(tmp_path: Path) -> None:
    """"shared token" sits in Alpha and Beta: Enter steps 1/2 → 2/2 → 1/2."""
    window = _open(tmp_path)
    alpha, beta = _center_of(window, "Alpha"), _center_of(window, "Beta")

    _search(window, "shared token")
    assert "1/2" in window.statusBar().currentMessage()
    first_center = _view_center(window)

    _box(window).returnPressed.emit()
    assert "2/2" in window.statusBar().currentMessage()
    second_center = _view_center(window)
    assert first_center != second_center

    _box(window).returnPressed.emit()
    assert "1/2" in window.statusBar().currentMessage()
    assert _view_center(window) == first_center

    hits = {hit.card_id for hit in window._hits}
    assert {alpha.card.card_id, beta.card.card_id} == hits


def test_a_new_document_resets_the_hits(tmp_path: Path) -> None:
    window = _open(tmp_path)
    _search(window, "shared token")
    assert window._hits

    other = tmp_path / "other.md"
    other.write_text("# Zeta\n\nzeta body\n", encoding="utf-8")
    assert window.open_path(other) is True

    assert window._hits == () and window._hit_index == -1
    _search(window, "shared token")
    assert "未找到" in window.statusBar().currentMessage()
    _search(window, "Zeta")
    assert "1/1" in window.statusBar().currentMessage()


def test_an_empty_query_says_what_to_do(tmp_path: Path) -> None:
    window = _open(tmp_path)
    _search(window, "   ")
    assert "输入关键字" in window.statusBar().currentMessage()


def test_searching_without_a_document_does_not_crash() -> None:
    window = MainWindow(persist=False, renderer=StubRenderer())  # type: ignore[arg-type]
    _search(window, "anything")
    assert "先打开" in window.statusBar().currentMessage()


def test_surrounding_whitespace_is_ignored(tmp_path: Path) -> None:
    window = _open(tmp_path)
    _search(window, "  Gamma  ")
    assert "1/1" in window.statusBar().currentMessage()
