"""T-073 / T-074: the app must own its own chrome colours, and [TOC] stays dark.

T-073 evidence: with Windows in dark mode and the app on the light theme the toolbar and menu bar
turned black (they kept the operating system's QPalette, because the window stylesheet only named
QMainWindow/QToolBar/QStatusBar/QDockWidget/QTreeWidget and one QToolButton).
T-074: the markdown ``[TOC]`` card must read as dark in both themes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from mcwr.domain.models import CardKind
from mcwr.interfaces.gui.main_window import MainWindow
from mcwr.interfaces.gui.theme import DARK, LIGHT, ThemeMode, card_fill, content_palette

DOCUMENT = """[TOC]

# Heading G

body text
"""

TOOLBAR_BAND = 44  # the toolbar strip at the top of the window


class StubRenderer:
    last_error = None

    def render(self, *, kind, source, scale, theme: str = "light"):  # noqa: ANN001, ANN201
        return None


def _dark_os_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#202020"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#E6EDF3"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#2B2B2B"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#E6EDF3"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#2B2B2B"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#E6EDF3"))
    return palette


def _chrome_band_luminance(window: MainWindow) -> float:
    image = window.grab().toImage()
    total = 0.0
    counted = 0
    for y in range(0, min(TOOLBAR_BAND, image.height()), 2):
        for x in range(0, image.width(), 2):
            total += image.pixelColor(x, y).lightnessF()
            counted += 1
    assert counted, "the toolbar band must exist"
    return total / counted


@pytest.fixture
def window(tmp_path: Path) -> MainWindow:
    document = tmp_path / "chrome.md"
    document.write_text(DOCUMENT, encoding="utf-8")
    window = MainWindow(persist=False, renderer=StubRenderer())  # type: ignore[arg-type]
    window.resize(1000, 700)
    window.show()
    assert window.open_path(document) is True
    window.apply_theme(ThemeMode.LIGHT, remember=False)
    for _ in range(4):
        QApplication.processEvents()
    return window


def test_chrome_stays_light_under_a_dark_operating_system_palette(window: MainWindow) -> None:
    """The toolbar must not turn black just because Windows is in dark mode (T-073)."""
    previous = QApplication.palette()
    QApplication.setPalette(_dark_os_palette())
    try:
        window.apply_theme(ThemeMode.LIGHT, remember=False)
        for _ in range(4):
            QApplication.processEvents()
        luminance = _chrome_band_luminance(window)
    finally:
        QApplication.setPalette(previous)

    assert luminance > 0.75, (
        f"the toolbar band is dark (mean luminance {luminance:.2f}) while the app theme is light: "
        "the chrome is inheriting the operating system's palette (T-073)"
    )


def test_the_toc_card_is_dark_in_both_themes() -> None:
    """``[TOC]`` keeps the dark fill and the dark palette's readable text (T-074)."""
    assert card_fill(LIGHT, CardKind.TOC) == DARK.card_bg
    assert card_fill(DARK, CardKind.TOC) == DARK.card_bg

    assert content_palette(LIGHT, CardKind.TOC) is DARK, "TOC content must use the dark palette"
    assert content_palette(LIGHT, CardKind.HEADING) is LIGHT
    assert content_palette(DARK, CardKind.CODE) is DARK


def test_the_toc_card_paints_dark(window: MainWindow) -> None:
    """Pixel-level: the TOC card's own fill is dark even in the light theme."""
    item = next(item for item in window.card_items.values() if item.card.kind is CardKind.TOC)
    # Grab the *viewport*: mapFromScene() speaks viewport coordinates, and window.grab() would
    # include the toolbar/dock offset (the mistake that sampled the board instead of the card).
    image = window.view.viewport().grab().toImage()
    image.setDevicePixelRatio(1.0)
    scene_point = item.scenePos() + type(item.scenePos())(item.card_width - 12.0, 8.0)
    view_point = window.view.mapFromScene(scene_point)
    colour = image.pixelColor(view_point.x(), view_point.y())
    assert colour.lightnessF() < 0.4, (
        f"the [TOC] card fill is light ({colour.name()}); it must stay dark in every theme (T-074)"
    )
