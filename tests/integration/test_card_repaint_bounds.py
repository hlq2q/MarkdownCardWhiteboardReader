"""T-081: a moved card must not leave a smear, so boundingRect() covers what paint() draws.

The trail the user saw: the shadow (one pixel below the frame) and the selection outline
(outside the frame) were painted outside ``boundingRect()``, and Qt repaints a moved item only
through that rect -- a pan or a zoom forced the full repaint that wiped the leftovers.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import QApplication

from mcwr.interfaces.gui.card_item import PAINT_MARGIN
from mcwr.interfaces.gui.main_window import MainWindow
from mcwr.interfaces.gui.theme import SELECTED_WIDTH

DOCUMENT = """# Heading

body text

## Child

more text
"""


class StubRenderer:
    last_error = None

    def render(self, *, kind, source, scale, theme: str = "light"):  # noqa: ANN001, ANN201
        return None


@pytest.fixture
def window(tmp_path: Path) -> MainWindow:
    document = tmp_path / "bounds.md"
    document.write_text(DOCUMENT, encoding="utf-8")
    window = MainWindow(persist=False, renderer=StubRenderer())  # type: ignore[arg-type]
    window.resize(1000, 700)
    window.show()
    assert window.open_path(document) is True
    for _ in range(3):
        QApplication.processEvents()
    return window


def test_the_bounding_rect_covers_the_shadow_and_the_selection_outline(
    window: MainWindow,
) -> None:
    for item in window.card_items.values():
        rect = item.boundingRect()
        box = QRectF(0.0, 0.0, item.card_width, item.card_height)

        assert rect.contains(box), "the card box itself must be inside the repaint rect"
        frame_bottom = 0.5 + (item.card_height - 1.0)
        assert rect.bottom() >= frame_bottom + 1.0, (
            "the shadow is painted one pixel below the frame, so the repaint rect must reach it"
        )
        outline_outside = SELECTED_WIDTH / 2.0 - 0.5  # frame starts at 0.5
        assert rect.left() <= -outline_outside, "the selection outline is painted outside the frame"
        assert rect.right() >= item.card_width + outline_outside
        assert rect.top() <= -outline_outside
        assert rect.width() == pytest.approx(item.card_width + 2 * PAINT_MARGIN)


def test_hit_testing_stays_tight(window: MainWindow) -> None:
    """The paint margin must not make a card grabbable from outside its box (T-081).

    Asserted behaviourally: a point inside the box is in the shape, a point inside the paint margin
    (1.5 px outside the box) is not. Comparing ``shape().boundingRect()`` exactly would trip over the
    rounded corners.
    """
    for item in window.card_items.values():
        wide, high = item.card_width, item.card_height
        path = item.shape()
        assert path.contains(QPointF(wide / 2.0, high / 2.0))
        assert not path.contains(QPointF(wide + 1.5, high / 2.0))
        assert not path.contains(QPointF(-1.5, high / 2.0))
        assert not path.contains(QPointF(wide / 2.0, -1.5))
