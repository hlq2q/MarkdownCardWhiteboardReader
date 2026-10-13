"""T-031 acceptance: only what is on screen is rasterized (NFR-3, viewport lazy loading).

The document below gives every heading its own math block, so a 121-card board carries 60
rich cards. At "fit" zoom they are all far below the on-screen size floor and nothing is
rendered; at 100% only the cards near the viewport are — which is the whole point of the
change, and what makes a much larger card limit affordable.
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from mcwr.application.features.render_card.service import web_source
from mcwr.domain.enums import CardKind
from mcwr.interfaces.gui.card_item import CardItem
from mcwr.interfaces.gui.main_window import MAX_LIVE_PIXMAPS, MainWindow
from mcwr.interfaces.gui.theme import LIGHT, MIN_LEGIBLE_ON_SCREEN_WIDTH

SECTIONS = 60


class RecordingRenderer:
    """Records what it was asked to rasterize; never starts WebEngine, never returns an image."""

    last_error: str | None = None

    def __init__(self) -> None:
        self.calls: list[str] = []

    def render(
        self, *, kind: object, source: str, scale: float, theme: str = "light"
    ) -> Path | None:
        del kind, scale, theme
        self.calls.append(source)
        return None


def _document(sections: int = SECTIONS) -> str:
    return "\n".join(
        f"# Section {index}\n\n$$x_{{{index}}}$$\n" for index in range(sections)
    )


def _open(tmp_path: Path) -> tuple[MainWindow, RecordingRenderer]:
    """Open the board and let the initial fit settle; the record starts clean after that.

    Opening queues the viewport *as it was before* ``fit_cards`` runs (a few cards at the old
    zoom), which is legitimate work rather than a defect — the tests measure the steady state,
    so the recording is cleared once the fit has been applied.
    """
    document = tmp_path / "lazy.md"
    document.write_text(_document(), encoding="utf-8")
    renderer = RecordingRenderer()
    window = MainWindow(persist=False, renderer=renderer)  # type: ignore[arg-type]
    window.show()
    assert window.open_path(document) is True
    _settle()
    renderer.calls.clear()
    return window, renderer


def _settle(cycles: int = 70) -> None:
    """Let the debounced timers fire and the queue drain (real time, not just events)."""
    app = QApplication.instance()
    assert app is not None
    for _ in range(cycles):
        app.processEvents()
        time.sleep(0.01)


def _rich_items(window: MainWindow) -> list[CardItem]:
    return [
        item
        for item in window.card_items.values()
        if item.card.kind in {CardKind.MATH_BLOCK, CardKind.MERMAID}
    ]


def _source_of(window: MainWindow, item: CardItem) -> str | None:
    return web_source(item.card, window.session.blocks, item.card.block_index or -1)


def _rendered_keys(window: MainWindow) -> set[str]:
    """The raster keys of the cards the queue is allowed to touch right now."""
    keys: set[str] = set()
    for card_id in window._render_candidates:
        item = window.card_items.get(card_id)
        if item is not None:
            source = _source_of(window, item)
            if source is not None:
                keys.add(source)
    return keys


def test_a_board_that_fits_on_screen_renders_nothing_because_every_card_is_too_small(
    tmp_path: Path,
) -> None:
    """The T-031 floor: at fit zoom the cards are unreadable whether or not there is a bitmap."""
    window, renderer = _open(tmp_path)
    assert window.view.zoom_percent() < 100.0, "the board must not fit at 100%"
    _settle()

    assert len(_rich_items(window)) == SECTIONS, "every heading has a math card"
    assert renderer.calls == [], "nothing on screen is big enough to be worth a browser round"
    assert all(not item.is_pending for item in _rich_items(window))


def test_zooming_in_renders_only_the_cards_near_the_viewport(tmp_path: Path) -> None:
    window, renderer = _open(tmp_path)
    rich = _rich_items(window)
    first = rich[0]

    window.view.set_zoom(100.0)
    window.view.centerOn(first.sceneBoundingRect().center())
    _settle()

    assert renderer.calls, "the cards around the viewport must be rendered"
    assert set(renderer.calls) == _rendered_keys(window), "exactly the queued neighbourhood"
    assert len(renderer.calls) <= 12, f"only the neighbourhood: {len(renderer.calls)} calls"
    assert _source_of(window, rich[-1]) not in renderer.calls, (
        "a card a board away must not be rasterized"
    )


def test_the_nearest_card_is_rendered_first(tmp_path: Path) -> None:
    window, renderer = _open(tmp_path)
    target = _rich_items(window)[2]
    window.view.set_zoom(100.0)
    window.view.centerOn(target.sceneBoundingRect().center())
    _settle()

    assert renderer.calls, "something must have been rendered"
    assert renderer.calls[0] == _source_of(window, target), (
        f"the card under the viewport centre goes first, got {renderer.calls[0]}"
    )


def test_scrolling_to_a_card_renders_it(tmp_path: Path) -> None:
    window, renderer = _open(tmp_path)
    rich = _rich_items(window)
    first, last = rich[0], rich[-1]
    last_source = _source_of(window, last)
    assert last_source is not None

    window.view.set_zoom(100.0)
    window.view.centerOn(first.sceneBoundingRect().center())
    _settle()
    assert last_source not in renderer.calls

    window.view.centerOn(last.sceneBoundingRect().center())
    _settle()

    assert last_source in renderer.calls, "scrolling there must rasterize it"


def test_a_card_hidden_by_a_folded_ancestor_is_never_rendered(tmp_path: Path) -> None:
    """Folding a section used to queue its math cards anyway; the viewport rule drops them."""
    window, renderer = _open(tmp_path)
    first = _rich_items(window)[0]
    document = window.session.document
    assert document is not None
    parent_id = document.tree.cards[first.card.card_id].parent_id
    assert parent_id is not None
    source = _source_of(window, first)
    assert source is not None

    window.view.set_zoom(100.0)
    window.session.fold(parent_id)
    window.view.centerOn(first.sceneBoundingRect().center())
    _settle()

    assert first.isVisible() is False
    assert source not in renderer.calls, "a hidden card must not be rasterized"
    assert first.is_pending is False


def test_live_rasters_are_released_once_they_are_far_off_screen(tmp_path: Path) -> None:
    """The in-memory cache is bounded: scrolling a long board does not grow it without end."""
    window, _ = _open(tmp_path)
    rich = _rich_items(window)
    window.view.set_zoom(100.0)
    window.view.centerOn(rich[0].sceneBoundingRect().center())
    QApplication.instance().processEvents()  # type: ignore[union-attr]

    def key(card_id: str) -> tuple[str, float, str]:
        return (card_id, window._current_bucket(), LIGHT.theme.value)

    visible = rich[0].card.card_id
    far = rich[-1].card.card_id
    window._pixmaps[key(far)] = QPixmap(2, 2)
    for index in range(MAX_LIVE_PIXMAPS + 1):
        window._pixmaps[key(f"filler-{index}")] = QPixmap(2, 2)
    window._pixmaps[key(visible)] = QPixmap(2, 2)

    window._release_offscreen_pixmaps()

    assert len(window._pixmaps) <= MAX_LIVE_PIXMAPS
    assert key(visible) in window._pixmaps, "what is on screen keeps its raster"
    assert key(far) not in window._pixmaps, "what is far off screen is released"


def test_the_floor_is_the_value_the_user_approved() -> None:
    """T-031's render floor and T-033's paint floor are the same number (D-042)."""
    assert MIN_LEGIBLE_ON_SCREEN_WIDTH == 160.0
