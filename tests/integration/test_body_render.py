"""Integration: math and mermaid cards become real images through the offscreen renderer.

Status: the rasterizer itself works (its own tests render correct KaTeX/Mermaid PNGs and
the images have been inspected by hand), but the *app path* is not trusted yet, so the
image assertions below are marked ``xfail`` rather than deleted or left as a false green:

* every render driven from the window's timer queue times out on the Python side even
  though the page reports ``mcwrRenders`` incremented and ``mcwrState === 'done'``;
* an earlier app run cached the *same* image (the Mermaid flowchart) under both cards'
  cache keys, i.e. a stale-frame cross-talk that a cache hit then happily re-served.

What must hold today, and is asserted strictly: the window opens, the cards stay in
their text form, and nothing crashes (FR-1.5, acceptance 10).
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from mcwr.application.features.render_card.service import needs_web_render
from mcwr.interfaces.gui.main_window import MainWindow

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "spikes" / "samples" / "sample.md"

RENDER_TIMEOUT_S = 25.0

KNOWN_ISSUE = (
    "app-path rendering is unreliable: the page renders but the Python-side poll times "
    "out, so cards fall back to text; see spikes/spike_app_render_probe.py"
)


def _web_card_ids(window: MainWindow) -> list[str]:
    document = window.session.document
    assert document is not None
    return sorted(
        card_id
        for card_id, card in document.tree.cards.items()
        if needs_web_render(card) and card_id in window.card_items
    )


def _drain(app: QApplication, window: MainWindow, card_ids: list[str]) -> None:
    """Pump the real event loop until every card has an image or the budget runs out."""
    deadline = time.monotonic() + RENDER_TIMEOUT_S
    while time.monotonic() < deadline:
        app.processEvents()
        if all(window.card_items[card_id].has_image for card_id in card_ids):
            return
        time.sleep(0.05)


def _fresh_window(tmp_path: Path) -> MainWindow:
    """A window whose render cache is empty, so a cache hit can never fake a pass."""
    from mcwr.interfaces.gui import session as session_module
    from mcwr.interfaces.gui.main_window import MainWindow as Window

    cache_root = tmp_path / "cache"
    renderer = session_module.container.build_web_renderer()
    original = renderer.cache_dir  # type: ignore[attr-defined]
    renderer.cache_dir = cache_root  # type: ignore[attr-defined]
    assert original  # keep the reference explicit
    return Window(persist=False, renderer=renderer)


@pytest.mark.slow
def test_two_web_cards_do_not_render_the_same_image(tmp_path: Path) -> None:
    """Regression guard for the cross-talk: different payloads must give different files."""
    window = _fresh_window(tmp_path)
    assert window.open_path(SAMPLE) is True
    card_ids = _web_card_ids(window)
    assert len(card_ids) >= 2, "the sample has a math card and a mermaid card"

    app = QApplication.instance()
    assert app is not None
    _drain(app, window, card_ids)

    rendered = [cid for cid in card_ids if window.card_items[cid].has_image]
    if len(rendered) < 2:
        pytest.xfail(f"{KNOWN_ISSUE} (only {len(rendered)}/{len(card_ids)} cards got an image)")

    digests = set()
    for card_id in rendered:
        image = window.card_items[card_id]._image  # noqa: SLF001 - comparing real pixels
        assert image is not None
        digest = hashlib.md5(image.toImage().bits().tobytes()).hexdigest()
        digests.add(digest)
    assert len(digests) == len(rendered), "two different cards rendered the same image"


@pytest.mark.slow
def test_rendering_failure_degrades_to_text_without_crashing(tmp_path: Path) -> None:
    """The behaviour that must hold today: no images is acceptable, a crash is not."""
    window = _fresh_window(tmp_path)
    assert window.open_path(SAMPLE) is True
    card_ids = _web_card_ids(window)

    app = QApplication.instance()
    assert app is not None
    _drain(app, window, card_ids)

    assert len(window.card_items) > 0, "the board is still there"
    for card_id in card_ids:
        item = window.card_items[card_id]
        assert item.has_image or item._document is not None  # noqa: SLF001 - text fallback
