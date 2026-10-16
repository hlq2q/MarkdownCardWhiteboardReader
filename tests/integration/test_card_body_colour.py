"""T-071: the card body must not inherit the operating system's colours.

The bug: ``QTextDocument.drawContents()`` builds its own paint context from
``QGuiApplication.palette()``. With Windows in dark mode and the app on the light theme, body text
was painted light-grey on the light card -- the "some fonts have poor contrast" report -- while
headings, links and code stayed readable, because the document stylesheet pins those explicitly.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QImage, QPainter, QPalette
from PySide6.QtWidgets import QApplication, QStyleOptionGraphicsItem

from mcwr.interfaces.gui.card_item import CardItem
from mcwr.interfaces.gui.main_window import MainWindow

CARD_FILL = "#FDFDFE"  # LIGHT.card_bg
DOCUMENT = """# G

text g needs to be readable

## P

text p also readable
"""


class StubRenderer:
    last_error = None

    def render(self, *, kind, source, scale, theme: str = "light"):  # noqa: ANN001, ANN201
        return None


def _settle() -> None:
    for _ in range(3):
        QApplication.processEvents()


@pytest.fixture
def window(tmp_path: Path) -> MainWindow:
    document = tmp_path / "body.md"
    document.write_text(DOCUMENT, encoding="utf-8")
    window = MainWindow(persist=False, renderer=StubRenderer())  # type: ignore[arg-type]
    window.resize(1200, 900)
    window.show()
    assert window.open_path(document) is True
    _settle()
    return window


def _body_ink(item: CardItem) -> tuple[int, float]:
    """Dark pixels in the body area and their mean luminance: the body text inked on the card."""
    rect = item.body_rect()
    image = QImage(int(item.card_width) + 2, int(item.card_height) + 2, QImage.Format.Format_RGB32)
    image.fill(QColor(CARD_FILL))
    painter = QPainter(image)
    item.paint(painter, QStyleOptionGraphicsItem(), None)
    painter.end()

    dark = 0
    total = 0.0
    for y in range(max(int(rect.top()), 0), min(int(rect.bottom()), image.height())):
        for x in range(max(int(rect.left()), 0), min(int(rect.right()), image.width())):
            luminance = image.pixelColor(x, y).lightnessF()
            if luminance < 0.45:  # clearly darker than the card fill
                dark += 1
                total += luminance
    return dark, (total / dark if dark else 0.0)


def test_body_text_is_dark_even_when_the_system_palette_is_dark(window: MainWindow) -> None:
    """A dark OS palette must not leak into the light card's body (the T-071 report)."""
    item = next(iter(window.card_items.values()))
    dark_before, mean_before = _body_ink(item)
    assert dark_before > 20, "the fixture must actually paint body text"

    dark_palette = QPalette()
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText):
        dark_palette.setColor(role, QColor("#E6EDF3"))  # light text, as a dark OS theme provides
    dark_palette.setColor(QPalette.ColorRole.Base, QColor("#191D22"))
    dark_palette.setColor(QPalette.ColorRole.Window, QColor("#191D22"))

    previous = QApplication.palette()
    QApplication.setPalette(dark_palette)
    try:
        dark_after, mean_after = _body_ink(item)
    finally:
        QApplication.setPalette(previous)

    assert (dark_after, mean_after) == pytest.approx(
        (dark_before, mean_before), rel=0.25, abs=1.0
    ), (
        "the card body followed the operating system's palette: body text is inheriting it instead "
        "of the app theme (T-071)"
    )
