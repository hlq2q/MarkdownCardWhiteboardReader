"""A scaled card and everything inside it must fit, and stay put across a refresh (E-033/T-064)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from mcwr.interfaces.gui.main_window import MainWindow
from mcwr.interfaces.gui.theme import HEADER_HEIGHT, PADDING

DOCUMENT = """# Top

top body

## Free parent

parent body line

### Code child

```python
def greet(name):
    return "hi " + name

for index in range(3):
    print(greet(str(index)))
```

### Text child

A paragraph long enough to wrap over a couple of lines at the natural width, so its measured height
depends on the width it is laid out at.
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
    document = tmp_path / "scale.md"
    document.write_text(DOCUMENT, encoding="utf-8")
    window = MainWindow(persist=False, renderer=StubRenderer())  # type: ignore[arg-type]
    window.resize(1400, 900)
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


def test_a_scaled_card_keeps_its_height_across_refreshes(window: MainWindow) -> None:
    """E-033: the measurement is a rendered height, so the factor must not be applied twice."""
    code = _id(window, "python")
    window.session.detach(code)
    _settle()
    assert window.session.scale_card(code, 1.5) is True
    _settle()

    item = window.card_items[code]
    assert item.effective_scale == pytest.approx(1.5)
    scaled = item.card_height
    rendered = item.measured_body_height() or 0.0
    assert scaled == pytest.approx(HEADER_HEIGHT * 1.5 + rendered + 2 * PADDING, abs=2.0)

    window._refresh()
    _settle()
    assert window.session.layouts[code].scale == pytest.approx(1.5), "the factor survives a refresh"
    assert window.card_items[code].card_height == pytest.approx(scaled, abs=1.0), (
        "a refresh must not scale the card a second time"
    )


def test_a_child_inside_a_scaled_card_grows_with_it(window: MainWindow) -> None:
    """E-033: the child's box scales too, otherwise its content is clipped."""
    free = _id(window, "Free parent")
    window.session.detach(free)
    _settle()
    assert window.session.scale_card(free, 1.5) is True
    _settle()

    heading = window.card_items[_id(window, "Code child")]
    assert heading.effective_scale == pytest.approx(1.5)
    assert heading.header_height() == pytest.approx(HEADER_HEIGHT * 1.5, abs=0.5)
    assert heading.card_height > HEADER_HEIGHT * 1.5, "its code card is still inside it"

    window.session.detach(_id(window, "python"))  # now it has nothing left to place
    _settle()
    assert window.card_items[_id(window, "Code child")].card_height == pytest.approx(
        HEADER_HEIGHT * 1.5, abs=0.5
    ), "a title-bar-only card (T-059) scales exactly with its header"

    text = window.card_items[_id(window, "Text child")]
    available = text.card_height - text.header_height() - 2 * PADDING
    assert available >= (text.measured_body_height() or 0.0) - 1.0, "the text must not be clipped"


def test_the_effective_scale_comes_from_the_layout(window: MainWindow) -> None:
    """One source of truth (T-064): the item draws with exactly what the placer computed."""
    free = _id(window, "Free parent")
    window.session.detach(free)
    _settle()
    assert window.session.scale_card(free, 1.25) is True
    _settle()

    for card_id, layout in window.session.layouts.items():
        item = window.card_items.get(card_id)
        if item is not None:
            assert item.effective_scale == pytest.approx(layout.effective_scale)
