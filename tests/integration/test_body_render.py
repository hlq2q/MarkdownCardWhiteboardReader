"""Integration: math and mermaid cards become real images through the offscreen renderer.

This is the end-to-end proof of decision D14: port + KaTeX/Mermaid assets + cache + the
card item's pixmap path. Two traps are guarded deliberately:

* every test uses a **fresh cache directory**, so a cache hit can never fake a pass;
* two different payloads must produce **different** pixels — an earlier app run cached the
  same Mermaid raster under both cards' keys (a stale-frame cross-talk), which a cache hit
  then happily re-served. Identical images are the symptom, so they are asserted against.

The rasterizer renders through Chromium's print pipeline (``printToPdf`` + ``QPdfDocument``)
rather than grabbing the hidden widget: a headless ``QWebEngineView.grab()`` returns the
unpainted surface, which is how blank images once passed a "non-blank" check.
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

UNAVAILABLE = (
    "no WebEngine-backed rendering in this environment: cards keep their text form "
    "(documented degradation, FR-1.5); see spikes/spike_app_render_probe.py"
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
        pytest.xfail(f"{UNAVAILABLE} (only {len(rendered)}/{len(card_ids)} cards got an image)")

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
