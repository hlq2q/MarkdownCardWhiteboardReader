"""T-033 acceptance: the background grid has a device-pixel floor.

The overview slowness (43-47 ms per frame on a 1000-card board) came from this background, not
from the cards: at 10 % zoom the exposed scene rect is ~11240x8460 units, so a 24-unit grid
means hundreds of scene-long antialiased lines — about 40 ms of the 46 ms frame. Below four
device pixels of spacing the mesh is a flat tint, so it is skipped (D-042).
"""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter

from mcwr.interfaces.gui.board_view import MIN_GRID_DEVICE_STEP, BoardScene
from mcwr.interfaces.gui.theme import GRID_STEP, LIGHT


def _paint_background(scale: float, *, size: int = 120) -> QImage:
    """Draw the scene background through a painter scaled like the view at ``scale``."""
    scene = BoardScene(palette=LIGHT)
    image = QImage(size, size, QImage.Format.Format_RGB32)
    image.fill(QColor(LIGHT.board_bg))
    painter = QPainter(image)
    painter.scale(scale, scale)
    visible = QRectF(0.0, 0.0, size / scale, size / scale)
    scene.drawBackground(painter, visible)
    painter.end()
    return image


def _distinct_colours(image: QImage) -> set[str]:
    return {
        image.pixelColor(x, y).name()
        for y in range(image.height())
        for x in range(image.width())
    }


def test_the_floor_is_eight_device_pixels() -> None:
    assert MIN_GRID_DEVICE_STEP == 8.0


def test_the_grid_is_drawn_at_reading_zoom() -> None:
    """At 100 % the grid spacing is GRID_STEP device px, far above the floor."""
    assert GRID_STEP * 1.0 >= MIN_GRID_DEVICE_STEP
    colours = _distinct_colours(_paint_background(1.0))
    assert len(colours) >= 2, f"the grid must be visible at 100 %, got {colours}"


def test_the_grid_is_skipped_when_it_would_be_a_tint() -> None:
    """At 10 % the spacing is 2.4 device px: below the floor, so only the fill is painted."""
    scale = 0.10
    assert GRID_STEP * scale < MIN_GRID_DEVICE_STEP
    colours = _distinct_colours(_paint_background(scale))
    assert colours == {QColor(LIGHT.board_bg).name()}, f"nothing but the fill, got {colours}"


def test_the_boundary_is_exactly_where_the_constant_says() -> None:
    """Just above the floor the grid comes back; just below it stays away."""
    just_above = (MIN_GRID_DEVICE_STEP + 0.1) / GRID_STEP
    just_below = (MIN_GRID_DEVICE_STEP - 0.1) / GRID_STEP
    assert len(_distinct_colours(_paint_background(just_above))) >= 2
    assert len(_distinct_colours(_paint_background(just_below))) == 1


def test_the_line_count_stays_bounded_at_any_zoom() -> None:
    """The device floor also caps the work: spacing >= 4 px over a 1750 px viewport is < 900."""
    viewport_device_px = 1750.0
    worst_case = viewport_device_px / MIN_GRID_DEVICE_STEP
    assert worst_case * 2 < 900, f"a full frame can ask for {worst_case * 2:.0f} lines"
