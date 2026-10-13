"""T-020 acceptance: the dockable outline sidebar jumps to the heading it names.

The panel is a real ``QDockWidget`` holding a ``QTreeWidget``; the click goes through the
actual widget chain (``QTest`` on the tree's viewport), and the jump reuses the same
``_focus_card`` path as a TOC line, so what is asserted here is the behaviour the user sees.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDockWidget, QTreeWidget, QTreeWidgetItemIterator

from mcwr.interfaces.gui.main_window import OUTLINE_SHORTCUT, MainWindow
from mcwr.interfaces.gui.theme import DARK, LIGHT, ThemeMode

DOCUMENT = """[TOC]

# Alpha

alpha body

## Beta

beta body

### Gamma

gamma body

## Delta

delta body: enough content below the headings that "center on the card" is a real scroll
rather than a clamp at the end of the board, and tall enough to survive a 200% zoom.

### Epsilon

epsilon body.

# Zeta

zeta body.
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
    document = tmp_path / "outline.md"
    document.write_text(text, encoding="utf-8")
    window = MainWindow(persist=False, renderer=StubRenderer())  # type: ignore[arg-type]
    window.show()  # the tree and viewport need a real geometry for the click mapping
    assert window.open_path(document) is True
    window.view.set_zoom(200.0)  # keep the board bigger than the viewport (see the docstring)
    QApplication.instance().processEvents()  # type: ignore[union-attr]
    return window


def _tree(window: MainWindow) -> QTreeWidget:
    tree = window._outline
    assert tree is not None
    return tree


def _rows(tree: QTreeWidget) -> list[object]:
    iterator = QTreeWidgetItemIterator(tree)
    rows: list[object] = []
    while iterator.value() is not None:
        rows.append(iterator.value())
        iterator += 1
    return rows


def _rect_of(tree: QTreeWidget, row: object) -> object:
    return tree.visualItemRect(row)


def _click(tree: QTreeWidget, row: object) -> None:
    tree.scrollToItem(row)
    QApplication.instance().processEvents()  # type: ignore[union-attr]
    QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=_rect_of(tree, row).center())


def _view_center(window: MainWindow) -> object:
    return window.view.mapToScene(window.view.viewport().rect().center())


def test_the_outline_is_a_dockable_left_sidebar_with_the_heading_tree(tmp_path: Path) -> None:
    window = _open(tmp_path)
    dock = window._outline_dock
    assert isinstance(dock, QDockWidget)
    assert dock.isVisible()
    assert dock.allowedAreas() & Qt.DockWidgetArea.LeftDockWidgetArea
    assert dock.allowedAreas() & Qt.DockWidgetArea.RightDockWidgetArea
    assert window.dockWidgetArea(dock) == Qt.DockWidgetArea.LeftDockWidgetArea

    tree = _tree(window)
    labels = [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]
    assert labels == ["Alpha", "Zeta"], "top level = the H1 cards"
    alpha = tree.topLevelItem(0)
    assert [alpha.child(i).text(0) for i in range(alpha.childCount())] == ["Beta", "Delta"]
    beta = alpha.child(0)
    assert [beta.child(i).text(0) for i in range(beta.childCount())] == ["Gamma"]


def test_clicking_the_third_entry_centers_that_card(tmp_path: Path) -> None:
    window = _open(tmp_path)
    tree = _tree(window)
    rows = _rows(tree)
    assert len(rows) == 6, "every heading is listed"
    third = rows[2]
    assert third.text(0) == "Gamma"

    card_id = third.data(0, Qt.ItemDataRole.UserRole)
    target = window.card_items[card_id]
    # Park the view at the far end of the board first, so the jump has to move it.
    far = window.card_items[window.session.toc[-1].card_id]
    window.view.centerOn(far.sceneBoundingRect().center())
    assert not target.sceneBoundingRect().contains(_view_center(window))

    _click(tree, third)

    center = _view_center(window)
    expected = target.sceneBoundingRect().center()
    assert abs(center.x() - expected.x()) <= CENTER_TOLERANCE_PX, (center, expected)
    assert abs(center.y() - expected.y()) <= CENTER_TOLERANCE_PX, (center, expected)
    assert target.isSelected() is True
    assert "已定位" in window.statusBar().currentMessage()


def test_an_outline_jump_into_a_folded_section_unfolds_it_first(tmp_path: Path) -> None:
    window = _open(tmp_path)
    tree = _tree(window)
    rows = _rows(tree)
    gamma_row = next(row for row in rows if row.text(0) == "Gamma")
    card_id = gamma_row.data(0, Qt.ItemDataRole.UserRole)

    document = window.session.document
    assert document is not None
    beta_id = document.tree.cards[card_id].parent_id
    assert beta_id is not None
    window.session.fold(beta_id)
    QApplication.instance().processEvents()  # type: ignore[union-attr]
    assert window.card_items[card_id].isVisible() is False

    _click(tree, gamma_row)

    assert window.session.layouts[beta_id].collapsed is False
    assert window.card_items[card_id].isVisible() is True
    assert "已展开 1 层折叠祖先" in window.statusBar().currentMessage()


def test_the_outline_and_the_toc_card_list_the_same_headings(tmp_path: Path) -> None:
    window = _open(tmp_path)
    assert [row.text(0) for row in _rows(_tree(window))] == [
        entry.label for entry in window.session.toc
    ]


def test_the_outline_follows_a_refresh(tmp_path: Path) -> None:
    window = _open(tmp_path)
    before = len(_rows(_tree(window)))
    document = window.session.path
    assert document is not None
    document.write_text(DOCUMENT + "\n# Eta\n\neta body.\n", encoding="utf-8")

    assert window.session.refresh() is True

    labels = [row.text(0) for row in _rows(_tree(window))]
    assert len(labels) == before + 1
    assert labels[-1] == "Eta"


def test_the_outline_is_themed_with_the_window(tmp_path: Path) -> None:
    window = _open(tmp_path)
    window.apply_theme(ThemeMode.DARK)
    assert DARK.app_bg in window.styleSheet()
    assert DARK.text_primary in window.styleSheet()
    assert "QToolButton#outlineCollapse" in window.styleSheet(), "the collapse button too"


# ---------------------------------------------------------- collapsing (T-032)


def test_the_panel_has_a_collapse_button_that_hides_and_restores_it(tmp_path: Path) -> None:
    window = _open(tmp_path)
    dock = window._outline_dock
    assert isinstance(dock, QDockWidget)
    button = window._outline_collapse
    assert button is not None
    assert button.isVisible(), "the collapse control must be reachable, not hidden"
    assert "收起" in button.text()
    assert button.objectName() == "outlineCollapse"
    assert "QToolButton#outlineCollapse" in window.styleSheet(), (
        "the button must carry theme colours: with the default style-sheet colours it was "
        "unreadable in the dark theme (found by looking at the real screenshot, T-032)"
    )
    assert LIGHT.text_primary in window.styleSheet()

    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert dock.isVisible() is False
    assert "收起" in window.statusBar().currentMessage()

    # Collapsing hides the button with the panel, so coming back is the toolbar entry / Ctrl+B.
    toggle = dock.toggleViewAction()
    toggle.trigger()
    assert dock.isVisible() is True
    QApplication.instance().processEvents()  # type: ignore[union-attr]
    assert button.isVisible() is True
    assert "展开" in window.statusBar().currentMessage()


def test_the_ctrl_b_shortcut_toggles_the_panel(tmp_path: Path) -> None:
    window = _open(tmp_path)
    dock = window._outline_dock
    assert isinstance(dock, QDockWidget)
    action = window._outline_action
    assert action is not None
    assert action.shortcut().toString() == OUTLINE_SHORTCUT == "Ctrl+B"
    assert action.isChecked() is True

    QTest.keyClick(window, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)

    assert dock.isVisible() is False, "Ctrl+B must collapse the sidebar"
    assert action.isChecked() is False

    QTest.keyClick(window, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)

    assert dock.isVisible() is True
    assert action.isChecked() is True
