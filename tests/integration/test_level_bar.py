"""T-028 acceptance: the left depth stripe, checked on painted pixels.

The document below nests four headings under one big section, so a single board exercises
every tier: the big section is depth 0 (tier 1), ``Top`` depth 1, ``Second`` depth 2,
``Third`` depth 3 (tier 4) and ``Fourth`` depth 4 — which must reuse tier 4, not invent a
fifth colour.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QStyleOptionGraphicsItem

from mcwr.domain.enums import CardKind
from mcwr.interfaces.gui.card_item import CardItem
from mcwr.interfaces.gui.main_window import MainWindow
from mcwr.interfaces.gui.theme import (
    DARK,
    LEVEL_BAR_WIDTH,
    LIGHT,
    ThemeMode,
    card_fill,
    level_bar_colour,
)

DOCUMENT = """# Top

text

## Second

text

### Third

text

#### Fourth

text
"""

BAR_SAMPLE_X = 1
FILL_SAMPLE_X = 6


class StubRenderer:
    last_error = None

    def render(
        self, *, kind: object, source: str, scale: float, theme: str = "light"
    ) -> Path | None:
        del kind, source, scale, theme
        return None


def _open(tmp_path: Path) -> MainWindow:
    document = tmp_path / "depth.md"
    document.write_text(DOCUMENT, encoding="utf-8")
    window = MainWindow(persist=False, renderer=StubRenderer())  # type: ignore[arg-type]
    assert window.open_path(document) is True
    return window


def _paint(item: CardItem) -> QImage:
    image = QImage(int(item.card_width), int(item.card_height), QImage.Format.Format_RGB32)
    image.fill(0)
    painter = QPainter(image)
    item.paint(painter, QStyleOptionGraphicsItem(), None)
    painter.end()
    return image


def _card(window: MainWindow, title: str) -> CardItem:
    for item in window.card_items.values():
        if item.card.title == title and item.card.kind is CardKind.HEADING:
            return item
    raise AssertionError(f"no heading card titled {title!r}")


def _depth(window: MainWindow, item: CardItem) -> int:
    document = window.session.document
    assert document is not None
    return len(document.tree.ancestors(item.card.card_id))


def _row_colours(item: CardItem) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """(bar colour, fill colour) sampled inside the card body."""
    image = _paint(item)
    y = int(item.body_rect().center().y())
    bar = image.pixelColor(BAR_SAMPLE_X, y)
    fill = image.pixelColor(FILL_SAMPLE_X, y)
    return bar.getRgb()[:3], fill.getRgb()[:3]


def test_every_depth_gets_its_own_tier_colour(tmp_path: Path) -> None:
    window = _open(tmp_path)
    for title, expected_depth in (("Top", 1), ("Second", 2), ("Third", 3), ("Fourth", 4)):
        item = _card(window, title)
        depth = _depth(window, item)
        assert depth == expected_depth, (title, depth)
        bar, _ = _row_colours(item)
        assert bar == QColor(level_bar_colour(LIGHT, depth)).getRgb()[:3], (
            f"{title} at depth {depth} must carry tier {depth + 1}"
        )


def test_the_fifth_level_and_deeper_reuse_tier_four(tmp_path: Path) -> None:
    window = _open(tmp_path)
    third, fourth = _card(window, "Third"), _card(window, "Fourth")
    assert _depth(window, fourth) == 4
    assert _row_colours(third)[0] == _row_colours(fourth)[0], (
        "the 5th level must reuse the 4th tier instead of inventing a colour"
    )


def test_the_stripe_is_exactly_three_pixels_and_does_not_eat_the_fill(tmp_path: Path) -> None:
    window = _open(tmp_path)
    item = _card(window, "Third")
    image = _paint(item)
    y = int(item.body_rect().center().y())
    stripe = QColor(level_bar_colour(LIGHT, 3)).getRgb()[:3]
    fill = QColor(card_fill(LIGHT, CardKind.HEADING)).getRgb()[:3]
    assert image.pixelColor(BAR_SAMPLE_X, y).getRgb()[:3] == stripe
    assert image.pixelColor(FILL_SAMPLE_X, y).getRgb()[:3] == fill
    assert LEVEL_BAR_WIDTH == 3.0
    assert int(LEVEL_BAR_WIDTH) <= FILL_SAMPLE_X, "the sample point must sit outside the stripe"


def test_switching_the_theme_repaints_the_stripe_with_the_other_palette(tmp_path: Path) -> None:
    window = _open(tmp_path)
    item = _card(window, "Second")
    light_bar, light_fill = _row_colours(item)
    assert light_bar == QColor(level_bar_colour(LIGHT, 2)).getRgb()[:3]

    window.apply_theme(ThemeMode.DARK)
    dark_bar, dark_fill = _row_colours(item)
    assert dark_bar == QColor(level_bar_colour(DARK, 2)).getRgb()[:3]
    assert (dark_bar, dark_fill) != (light_bar, light_fill)
    for palette in (LIGHT, DARK):
        assert level_bar_colour(palette, 0) == palette.level_bar[0]
