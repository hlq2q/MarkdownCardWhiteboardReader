"""T-025 acceptance ②/③: a document past the card limit degrades instead of stalling.

200 cards is the D-023 limit; at 201 the board must still open, stay interactive and stop
asking the offscreen renderer for math/diagram rasters (D-029), showing their source text
instead. Everything here uses a recording renderer, so no test starts WebEngine.
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QStyleOptionGraphicsItem

from mcwr.domain.enums import CardKind
from mcwr.domain.models import MAX_CARDS
from mcwr.interfaces.gui.card_item import CardItem
from mcwr.interfaces.gui.main_window import MainWindow
from mcwr.interfaces.gui.theme import card_fill
from mcwr.shared.logging import logger

INTERACTIVE_BUDGET_S = 5.0


class RecordingRenderer:
    """Records what it was asked to render; never starts WebEngine, never returns an image."""

    last_error: str | None = None

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def render(
        self, *, kind: object, source: str, scale: float, theme: str = "light"
    ) -> Path | None:
        del source, scale
        self.calls.append((str(kind), theme))
        return None


def _write_document(path: Path, *, headings: int) -> Path:
    """A document with exactly ``headings + 2`` cards.

    One card per heading, one math and one mermaid card (no wrapper card exists any more). The tests
    assert the resulting count, so a change in the card rules fails loudly instead of
    silently testing the wrong side of the boundary.
    """
    parts: list[str] = [f"# H{index}\n\ntext {index}\n" for index in range(headings)]
    parts.append("$$\nE = mc^2\n$$\n")
    parts.append("```mermaid\ngraph TD; A-->B;\n```\n")
    path.write_text("\n".join(parts), encoding="utf-8")
    return path


def _drain(window: MainWindow, *, minimum_seconds: float = 0.6) -> None:
    """Run the deferred render queue to completion, or fail instead of hanging.

    Since T-031 the queue is *debounced* (zoom 400 ms, scroll 180 ms), so a drain that only
    spins the event loop would return before anything was ever queued.
    """
    app = QApplication.instance()
    assert app is not None
    started = time.monotonic()
    deadline = started + 10.0
    while time.monotonic() < deadline:
        app.processEvents()
        if time.monotonic() - started >= minimum_seconds and not any(
            item.is_pending for item in window.card_items.values()
        ):
            return
        time.sleep(0.01)
    raise AssertionError("the body render queue never drained")


def _ink_pixels(item: CardItem) -> int:
    """Pixels that clearly differ from the card's own fill: proof that content was drawn."""
    image = QImage(int(item.card_width), int(item.card_height), QImage.Format.Format_RGB32)
    image.fill(0)
    painter = QPainter(image)
    item.paint(painter, QStyleOptionGraphicsItem(), None)
    painter.end()

    fill = QColor(card_fill(item.visual_palette, item.card.kind))
    width, height, stride = image.width(), image.height(), image.bytesPerLine()
    bits = bytes(image.constBits())
    ink = 0
    for y in range(0, height, 2):
        row = bits[y * stride : (y + 1) * stride]
        for offset in range(0, min(len(row), width * 4), 4):
            pixel = QColor(row[offset + 2], row[offset + 1], row[offset])
            if abs(pixel.lightness() - fill.lightness()) > 90:
                ink += 1
    return ink


def _rich_card(window: MainWindow, kind: str) -> CardItem:
    for item in window.card_items.values():
        if item.card.kind.value == kind:
            return item
    raise AssertionError(f"the generated document has no {kind} card")


def test_a_document_of_exactly_the_limit_is_opened_with_rich_rendering(tmp_path: Path) -> None:
    """The boundary itself: the limit is not "degraded" (D-040)."""
    document = _write_document(tmp_path / "at-limit.md", headings=MAX_CARDS - 2)
    renderer = RecordingRenderer()
    window = MainWindow(persist=False, renderer=renderer)  # type: ignore[arg-type]

    assert window.open_path(document) is True
    assert window.session.card_count == MAX_CARDS
    assert window.session.over_limit is False

    # Since T-031 rendering is viewport-bound, so the boundary must be probed at a zoom where
    # a rich card is big enough on screen: fit zoom would (correctly) render nothing.
    rich = next(
        item for item in window.card_items.values() if item.card.kind is CardKind.MATH_BLOCK
    )
    window.view.set_zoom(100.0)
    window.view.centerOn(rich.sceneBoundingRect().center())
    _drain(window)

    assert renderer.calls, "at the limit the math/mermaid cards are still rasterized"
    assert {theme for _, theme in renderer.calls} == {window.theme.value}


def test_a_document_over_the_limit_degrades_and_stays_interactive(tmp_path: Path) -> None:
    """One card over the limit: opens fast, renders nothing offscreen, says why, and still works."""
    document = _write_document(tmp_path / "over-limit.md", headings=MAX_CARDS - 1)
    renderer = RecordingRenderer()
    window = MainWindow(persist=False, renderer=renderer)  # type: ignore[arg-type]

    logged: list[str] = []
    handler = logger().add(logged.append, level="WARNING", format="{message}")
    try:
        started = time.monotonic()
        assert window.open_path(document) is True
        elapsed = time.monotonic() - started
        _drain(window)
    finally:
        logger().remove(handler)

    assert window.session.card_count == MAX_CARDS + 1
    assert window.session.over_limit is True
    assert len(window.card_items) == MAX_CARDS + 1, "every card is still on the board"
    assert renderer.calls == [], "the offscreen path must not even be attempted"
    assert all(not item.has_image for item in window.card_items.values())
    assert all(not item.is_pending for item in window.card_items.values())

    assert "超限" in window.statusBar().currentMessage()
    notices = [text for text in logged if "rich rendering is off" in text]
    assert len(notices) == 1, f"exactly one notice per load, got {notices}"

    assert elapsed <= INTERACTIVE_BUDGET_S, f"opening took {elapsed:.2f}s"

    window.view.set_zoom(75.0)
    assert round(window.view.zoom_percent()) == 75
    window.session.restore_all()
    assert window.session.card_count == MAX_CARDS + 1


def test_the_degraded_math_card_draws_its_source_text(tmp_path: Path) -> None:
    """D-029 says "show the source", so the card must really paint it, not go blank."""
    document = _write_document(tmp_path / "over-limit.md", headings=MAX_CARDS - 2)
    window = MainWindow(persist=False, renderer=RecordingRenderer())  # type: ignore[arg-type]
    assert window.open_path(document) is True

    math_card = _rich_card(window, "math_block")
    assert math_card.has_image is False
    assert _ink_pixels(math_card) > 20, "the LaTeX source must be visible in the card"


def test_an_over_limit_document_can_still_be_refreshed(tmp_path: Path) -> None:
    """The degraded mode survives a refresh instead of flipping back to the heavy path."""
    document = _write_document(tmp_path / "over-limit.md", headings=MAX_CARDS - 2)
    renderer = RecordingRenderer()
    window = MainWindow(persist=False, renderer=renderer)  # type: ignore[arg-type]
    assert window.open_path(document) is True

    assert window.session.refresh() is True
    _drain(window)

    assert window.session.over_limit is True
    assert renderer.calls == []
