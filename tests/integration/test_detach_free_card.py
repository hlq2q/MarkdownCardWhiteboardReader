"""E-034: a free card floats, so detaching inside it must not resize its logical ancestor."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from mcwr.interfaces.gui.main_window import MainWindow

DOCUMENT = """# A

a body

## B

b body

### C

c body

# Z

z body
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
    for _ in range(3):
        app.processEvents()


@pytest.fixture
def window(tmp_path: Path) -> MainWindow:
    document = tmp_path / "abc.md"
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


def test_detaching_inside_a_free_card_leaves_the_ancestor_exactly_as_it_was(
    window: MainWindow,
) -> None:
    """E-034: B then C leave the flow one after another; A must not shrink either time."""
    a, b, c, z = (_id(window, title) for title in ("A", "B", "C", "Z"))
    with_children = window.session.layouts[a].height

    assert window.session.detach(b).changed is True  # B takes C with it, out of A
    _settle()
    assert window.session.layouts[a].height < with_children, "A does shrink when B leaves it"
    after_b = window.session.layouts[a].height
    z_after_b = window.session.layouts[z].y
    free_b = window.session.layouts[b].height

    assert window.session.detach(c).changed is True  # C leaves B -- inside a free card
    _settle()

    assert window.session.layouts[a].height == pytest.approx(after_b, abs=1.0), (
        "A no longer contains B, so B shrinking must not collapse A (that drift was the blank "
        "line: the layout said 0 while the item stayed 34)"
    )
    assert window.session.layouts[a].height > 0.0
    assert window.session.layouts[z].y == pytest.approx(z_after_b, abs=1.0), "no card may move"
    assert window.session.layouts[b].height < free_b, "B itself does shrink"


def test_a_refresh_finds_nothing_left_to_repair(window: MainWindow) -> None:
    """The refresh used to be what fixed A, which is how the drift showed up."""
    a, b, c = (_id(window, title) for title in ("A", "B", "C"))
    window.session.detach(b)
    _settle()
    window.session.detach(c)
    _settle()
    window._refresh()  # the first pass adopts the measured heights, so compare two settled passes
    _settle()
    settled = {card_id: window.session.layouts[card_id].height for card_id in (a, b, c)}
    z_y = window.session.layouts[_id(window, "Z")].y

    window._refresh()
    _settle()

    for card_id, height in settled.items():
        assert window.session.layouts[card_id].height == pytest.approx(height, abs=1.0)
    assert window.session.layouts[_id(window, "Z")].y == pytest.approx(z_y, abs=1.0)
