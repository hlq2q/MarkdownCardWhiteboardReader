"""A card is exactly as tall as the body it renders (T-049/E-029).

The layout used to run on the text estimator alone, and ``CardItem.paint`` clips the body to the
card's height: an over-estimate showed up as padding (a heading card was one line too tall because
its own heading block was counted, a code card paid for its ``` fences), and an under-estimate hid
content (a rendered table row is ~26 px, not the 20 px the estimator assumed, so long tables lost
their last rows). The view now measures every document and hands the heights back.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from mcwr.application.features.layout_board.service import LinearLayoutOptions
from mcwr.domain.enums import BlockKind
from mcwr.interfaces.gui.main_window import MainWindow
from mcwr.interfaces.gui.theme import HEADER_HEIGHT, PADDING

DOCUMENT = """# Text card

one short line

# Code card

```python
a = 1
b = 2
c = 3
```

# Long table

| col a | col b | col c |
| --- | --- | --- |
| 1 | 2 | 3 |
| 4 | 5 | 6 |
| 7 | 8 | 9 |
| 10 | 11 | 12 |
| 13 | 14 | 15 |
| 16 | 17 | 18 |
| 19 | 20 | 21 |
| 22 | 23 | 24 |
| 25 | 26 | 27 |
| 28 | 29 | 30 |
| 31 | 32 | 33 |
| 34 | 35 | 36 |
| 37 | 38 | 39 |
| 40 | 41 | 42 |
| 43 | 44 | 45 |

# Parent card

parent body line

## Child one

child body

## Child two

child body
"""


# The gap between sibling cards, which a heading-only parent leaves as its whole spacing (T-058).
SIBLING_GAP = LinearLayoutOptions().gap


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
    document = tmp_path / "heights.md"
    document.write_text(DOCUMENT, encoding="utf-8")
    window = MainWindow(persist=False, renderer=StubRenderer())  # type: ignore[arg-type]
    window.resize(1400, 1000)
    window.show()
    assert window.open_path(document) is True
    _settle()
    return window


def _childless_cards(window: MainWindow) -> list[tuple[str, object]]:
    document = window.session.document
    assert document is not None
    return [
        (card.title, window.card_items[card_id])
        for card_id, card in document.tree.cards.items()
        if not card.child_ids and card_id in window.card_items
    ]


def test_a_childless_card_is_exactly_its_measured_body(window: MainWindow) -> None:
    """No phantom padding: a 3-line code card pays for 3 lines, not for its fences too."""
    cards = _childless_cards(window)
    assert len(cards) >= 5
    for title, item in cards:
        measured = item.measured_body_height()
        if measured is None:
            continue
        expected = HEADER_HEIGHT + 2 * PADDING + measured
        assert item.card_height == pytest.approx(expected, abs=0.5), title


def test_no_measured_body_is_clipped(window: MainWindow) -> None:
    """A long table must show every row: the body it renders has to fit in the card."""
    for title, item in _childless_cards(window):
        measured = item.measured_body_height()
        if measured is None:
            continue
        assert measured <= item.card_height - HEADER_HEIGHT - 2 * PADDING + 0.5, title


def test_a_parents_first_child_keeps_the_documented_distance(window: MainWindow) -> None:
    """T-058: a heading-only parent leaves just the sibling gap, one with text keeps the padding.

    The gap is measured from the parent's body bottom, so a card whose own block is only its heading
    (its body measures ~0) must start its first child within the 8 px sibling gap, while a card that
    carries text keeps the usual bottom padding and stays under 44 px.
    """
    document = window.session.document
    assert document is not None
    checked = 0
    for card_id, card in document.tree.cards.items():
        item = window.card_items.get(card_id)
        if item is None or not card.child_ids:
            continue
        measured = item.measured_body_height()
        if measured is None:
            continue
        body_bottom = item.scenePos().y() + HEADER_HEIGHT + measured
        gap = window.session.layouts[card.child_ids[0]].y - body_bottom
        blocks = window.session.blocks
        has_body = any(
            blocks[index].kind is not BlockKind.HEADING
            for index in card.own_block_indexes
            if index in blocks
        )
        if has_body:
            assert 0.0 <= gap <= 44.0, (card.title, measured, gap)
        else:
            # The layout gives such a parent no body at all, so its first child sits one sibling gap
            # below the header. An empty document still *measures* a line, hence the 8 - measured.
            assert gap == pytest.approx(SIBLING_GAP - measured, abs=1.0), (
                card.title,
                measured,
                gap,
            )
        checked += 1
    assert checked >= 2
