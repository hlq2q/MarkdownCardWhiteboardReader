"""T-024 acceptance ③/④ at the window level: a theme switch repaints, never re-lays out.

These tests use a recording renderer and therefore no WebEngine (see
`tests/integration/conftest.py`); the rasterizer's own theme behaviour — a dark card really
rasterized on the dark fill, two themes never sharing a cache file — is covered next to its
source in `src/mcwr/infrastructure/test_web_renderer.py`.
"""

from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path

from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QStyleOptionGraphicsItem

from mcwr.domain.enums import CardKind
from mcwr.domain.models import CardLayout
from mcwr.interfaces.gui.card_item import CardItem
from mcwr.interfaces.gui.main_window import MainWindow
from mcwr.interfaces.gui.theme import DARK, LIGHT, Palette, ThemeMode, card_fill

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "spikes" / "samples" / "sample.md"


class RecordingRenderer:
    """A renderer that never starts WebEngine; it records which theme it was asked for."""

    last_error: str | None = None

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def render(
        self, *, kind: object, source: str, scale: float, theme: str = "light"
    ) -> Path | None:
        del source, scale
        self.calls.append((str(kind), theme))
        return None


def _drain(window: MainWindow) -> None:
    """Run the deferred render queue to completion, or fail instead of hanging."""
    app = QApplication.instance()
    assert app is not None
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        app.processEvents()
        if not any(item.is_pending for item in window.card_items.values()):
            return
        time.sleep(0.01)
    raise AssertionError("the body render queue never drained")


def _layout_snapshot(window: MainWindow) -> dict[str, dict[str, object]]:
    return {card_id: asdict(layout) for card_id, layout in window.session.layouts.items()}


def _paint(item: CardItem) -> QImage:
    """Draw one card item into an image the way the scene would."""
    image = QImage(int(item.card_width), int(item.card_height), QImage.Format.Format_RGB32)
    image.fill(0)
    painter = QPainter(image)
    item.paint(painter, QStyleOptionGraphicsItem(), None)
    painter.end()
    return image


def _fill_and_ink(image: QImage, palette: Palette, kind: CardKind) -> tuple[int, int]:
    """Count fill pixels and text pixels: proof the card is drawn *and* readable."""
    fill = QColor(card_fill(palette, kind))
    width, height, stride = image.width(), image.height(), image.bytesPerLine()
    bits = bytes(image.constBits())
    fill_count = 0
    ink_count = 0
    for y in range(0, height, 2):
        row = bits[y * stride : (y + 1) * stride]
        for offset in range(0, min(len(row), width * 4), 4):
            pixel = QColor(row[offset + 2], row[offset + 1], row[offset])
            if abs(pixel.red() - fill.red()) <= 6 and abs(
                pixel.green() - fill.green()
            ) <= 6 and abs(pixel.blue() - fill.blue()) <= 6:
                fill_count += 1
            elif abs(pixel.lightness() - fill.lightness()) > 90:
                ink_count += 1
    return fill_count, ink_count


def _first_card_with_own_text(window: MainWindow) -> CardItem:
    for item in window.card_items.values():
        if item.card.own_block_indexes and item.card.kind is not CardKind.HEADING:
            return item
    raise AssertionError("the sample has no card with its own content")


def test_switching_the_theme_changes_no_layout_field() -> None:
    """T-024 ③: the switch repaints; every CardLayout field stays byte-for-byte equal."""
    window = MainWindow(persist=False)
    assert window.open_path(SAMPLE) is True
    before = _layout_snapshot(window)
    document_before = window.session.document
    items_before = window.card_items
    assert before, "the sample must produce layouts"

    assert window.apply_theme(ThemeMode.DARK) is DARK.theme
    assert _layout_snapshot(window) == before, "a theme switch must not move or resize a card"
    assert window.session.document is document_before, "the document must not be re-parsed"
    assert window.card_items.keys() == items_before.keys(), "no card item was rebuilt"
    assert all(
        window.card_items[card_id] is items_before[card_id] for card_id in items_before
    ), "the very same item objects must be repainted, not recreated"

    assert window.theme_mode is ThemeMode.DARK
    assert window.visual_palette is DARK
    assert window.scene.visual_palette is DARK
    assert all(item.visual_palette is DARK for item in window.card_items.values())
    assert window.scene.backgroundBrush().color() == QColor(DARK.board_bg)

    assert window.apply_theme(ThemeMode.LIGHT) is LIGHT.theme
    assert _layout_snapshot(window) == before
    assert all(item.visual_palette is LIGHT for item in window.card_items.values())


def test_a_card_paints_readable_text_in_both_themes() -> None:
    """T-024 ④ for text cards: the same card stays legible on the dark fill and back."""
    window = MainWindow(persist=False)
    assert window.open_path(SAMPLE) is True
    item = _first_card_with_own_text(window)

    window.apply_theme(ThemeMode.DARK)
    dark_fill, dark_ink = _fill_and_ink(_paint(item), DARK, item.card.kind)
    window.apply_theme(ThemeMode.LIGHT)
    light_fill, light_ink = _fill_and_ink(_paint(item), LIGHT, item.card.kind)

    assert dark_fill > 200 and light_fill > 200, (dark_fill, light_fill)
    assert dark_ink > 20, f"only {dark_ink} readable pixels on the dark card"
    assert light_ink > 20, f"only {light_ink} readable pixels on the light card"
    assert QColor(card_fill(DARK, item.card.kind)).lightness() < 96
    assert QColor(card_fill(LIGHT, item.card.kind)).lightness() > 160


def test_switching_the_theme_re_renders_the_rich_cards_in_the_new_theme() -> None:
    """T-024 ④: the raster is theme-specific, so the switch must re-queue it (spec §5)."""
    renderer = RecordingRenderer()
    window = MainWindow(persist=False, renderer=renderer)  # type: ignore[arg-type]
    assert window.open_path(SAMPLE) is True
    _drain(window)
    assert {theme for _, theme in renderer.calls} == {"light"}

    renderer.calls.clear()
    window.apply_theme(ThemeMode.DARK)
    _drain(window)

    assert renderer.calls, "the math/mermaid cards must be re-rendered for the dark theme"
    assert {theme for _, theme in renderer.calls} == {"dark"}


def test_the_chosen_mode_is_remembered_across_windows(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """D-030: the preference is stored in the app data dir, and not in the Markdown folder."""
    monkeypatch.setenv("MCWR_APP_DIR", str(tmp_path / "appdata"))
    first = MainWindow(persist=True)
    assert first.theme_mode is ThemeMode.SYSTEM, "the default is follow-the-system"
    first.apply_theme(ThemeMode.DARK)
    assert (tmp_path / "appdata" / "settings.json").is_file()

    second = MainWindow(persist=True)
    assert second.theme_mode is ThemeMode.DARK
    assert (SAMPLE.parent / "settings.json").exists() is False, (
        "preferences never live next to the source Markdown (FR-8)"
    )


def test_a_non_persisting_window_does_not_write_a_preference(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("MCWR_APP_DIR", str(tmp_path / "appdata"))
    window = MainWindow(persist=False)
    window.apply_theme(ThemeMode.DARK)
    assert not (tmp_path / "appdata").exists(), "persist=False must not touch the disk"


def test_every_card_keeps_its_layout_object_identity() -> None:
    """A stronger form of ③: the layout objects themselves are the same instances."""
    window = MainWindow(persist=False)
    assert window.open_path(SAMPLE) is True
    before: dict[str, CardLayout] = dict(window.session.layouts)
    window.apply_theme(ThemeMode.DARK)
    after = window.session.layouts
    assert set(after) == set(before)
    assert all(after[card_id] is before[card_id] for card_id in before)
