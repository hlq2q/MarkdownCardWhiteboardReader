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
from PySide6.QtWidgets import (
    QApplication,
    QToolButton,
)

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


def test_hovering_the_toc_card_keeps_it_dark(window: MainWindow) -> None:
    """The light theme's hover fill must not flash the dark [TOC] card light (T-075)."""
    item = next(i for i in window.card_items.values() if i.card.kind is CardKind.TOC)

    rest = QColor(item._fill(LIGHT))
    assert rest.lightnessF() < 0.4, f"the TOC card's rest fill is light ({rest.name()})"

    item._hovered = True
    try:
        hovered = QColor(item._fill(LIGHT))
    finally:
        item._hovered = False
    assert hovered.lightnessF() < 0.4, (
        f"hovering paints the TOC card {hovered.name()} -- the dark card flashes light under the "
        "cursor because the hover fill came from the light theme (T-075)"
    )

    item._dragging = True
    try:
        dragged = QColor(item._fill(LIGHT))
    finally:
        item._dragging = False
    assert dragged.lightnessF() < 0.4, f"dragging paints the TOC card {dragged.name()} (T-075)"


REQUIRED_SELECTORS = (
    "QMainWindow",
    "QToolBar",
    "QStatusBar",
    "QDockWidget",
    "QDockWidget::title",
    "QDockWidget::close-button",
    "QDockWidget::float-button",
    "QMenuBar",
    "QMenu",
    "QToolTip",
    "QLabel",
    "QToolButton",
    "QComboBox",
    "QLineEdit",
    "QScrollBar",
    "QPushButton",
    "QTreeWidget",
)


def test_the_window_stylesheet_covers_every_chrome_widget(window: MainWindow) -> None:
    """Any widget left out keeps the OS palette -- exactly how T-073/T-077 happened (D-064).

    Add a selector here whenever the chrome gains a widget; the list is the reason the
    "light app on dark Windows" and "light app on light Windows" cases can be trusted.
    """
    sheet = window.styleSheet()
    missing = [selector for selector in REQUIRED_SELECTORS if selector not in sheet]
    assert not missing, f"these chrome widgets would fall back to the OS palette: {missing}"


REQUIRED_SELECTORS = (
    "QMainWindow",
    "QToolBar",
    "QStatusBar",
    "QDockWidget",
    "QDockWidget::title",
    "QDockWidget::close-button",
    "QDockWidget::float-button",
    "QMenuBar",
    "QMenu",
    "QToolTip",
    "QLabel",
    "QToolButton",
    "QComboBox",
    "QLineEdit",
    "QScrollBar",
    "QPushButton",
    "QTreeWidget",
)


def test_qt_can_parse_the_stylesheet(window: MainWindow) -> None:
    """A sheet Qt silently rejects is worse than no sheet: the chrome falls back to the OS (T-079).

    Qt reports a malformed sheet only through qWarning("Could not parse stylesheet"), so the pixels
    stay "styled-looking" in the source while the running app is unstyled. Catch it here instead.
    """
    from PySide6.QtCore import qInstallMessageHandler

    messages: list[str] = []

    def _collect(_mode, _context, message: str) -> None:  # noqa: ANN001
        messages.append(message)

    previous = qInstallMessageHandler(_collect)
    try:
        window.apply_theme(ThemeMode.LIGHT, remember=False)
        QApplication.processEvents()
    finally:
        qInstallMessageHandler(previous)

    offenders = [m for m in messages if "parse stylesheet" in m.lower()]
    assert not offenders, f"Qt rejected the stylesheet: {offenders}"


def test_the_dock_title_buttons_are_visible(window: MainWindow) -> None:
    """The float/close glyphs must be drawn from the palette, not by the style (T-080).

    They used to be near-white on the light title bar: the buttons were there, the glyphs were not.
    """
    from PySide6.QtCore import QPoint

    window.apply_theme(ThemeMode.LIGHT, remember=False)
    for _ in range(3):
        QApplication.processEvents()
    image = window.grab().toImage()
    for name in ("outlineFloat", "outlineClose"):
        button = window.findChild(QToolButton, name)
        assert button is not None, f"{name} is missing"
        origin = button.mapTo(window, QPoint(0, 0))
        ink = 0
        for y in range(max(origin.y(), 0), min(origin.y() + button.height(), image.height())):
            for x in range(max(origin.x(), 0), min(origin.x() + button.width(), image.width())):
                colour: QColor = image.pixelColor(x, y)
                if colour.lightnessF() < 0.55:  # clearly darker than the light title bar
                    ink += 1
        assert ink >= 6, (
            f"{name} draws (almost) no glyph: {ink} dark pixels -- the icon is probably still the "
            "style's near-white one (T-080)"
        )
