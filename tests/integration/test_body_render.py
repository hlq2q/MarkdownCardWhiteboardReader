"""Integration: math and mermaid cards become real images through the offscreen renderer.

Root cause of the flakiness this file used to hide behind an ``xfail`` (E-013): every test
built its own window and drained the render queue with a 25 s budget, while a **cold**
WebEngine start plus two rasters measured ~20 s per test — about 85 % of the budget. Any
extra load (a full-suite run, another Chromium already running) pushed it over and the
cards silently stayed text.

The fix is structural, not a longer timeout: **one** render session per module, a budget
with real headroom, and the measured cost asserted as a performance floor (decision D-022
item 10). The cross-talk guard stays, because an earlier app run cached the same Mermaid
raster under both cards' keys and a cache hit then re-served it.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from mcwr.application.features.render_card.service import needs_web_render
from mcwr.interfaces.gui.main_window import MainWindow

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "spikes" / "samples" / "sample.md"

RENDER_BUDGET_S = 90.0
"""Drain budget: ~4.5x the measured cold cost, so load cannot flip the result."""

PERF_CEILING_S = 60.0
"""If a cold render of the sample's two web cards exceeds this, that is a regression."""


@dataclass(frozen=True)
class RenderSession:
    """One cold-cache render run, shared by the assertions below."""

    window: MainWindow
    card_ids: tuple[str, ...]
    rendered: tuple[str, ...]
    elapsed: float

    @property
    def renderer_error(self) -> object:
        renderer = self.window._renderer  # noqa: SLF001 - reporting the wiring on purpose
        return getattr(renderer, "last_error", None)


def _web_card_ids(window: MainWindow) -> tuple[str, ...]:
    document = window.session.document
    assert document is not None
    return tuple(
        sorted(
            card_id
            for card_id, card in document.tree.cards.items()
            if needs_web_render(card) and card_id in window.card_items
        )
    )


def _drain(app: QApplication, window: MainWindow, card_ids: tuple[str, ...]) -> None:
    deadline = time.monotonic() + RENDER_BUDGET_S
    while time.monotonic() < deadline:
        app.processEvents()
        if all(window.card_items[card_id].has_image for card_id in card_ids):
            return
        time.sleep(0.05)


def _show_and_settle(window: MainWindow) -> None:
    """Give the window real geometry, then let the lazy queue recompute (T-031).

    Only cards on screen and at least ``MIN_RENDER_ON_SCREEN_WIDTH`` wide are rasterized, and
    an unshown window has no usable viewport — so without this the queue correctly stays empty
    and this module's "wait for the images" loop would look like a hang. The sample is small
    enough that its fit zoom keeps the math/mermaid cards above that floor.
    """
    window.resize(1400, 900)
    window.show()
    window.view.fit_cards()
    app = QApplication.instance()
    assert app is not None
    for _ in range(60):  # the zoom debounce is 400 ms (T-031)
        app.processEvents()
        time.sleep(0.01)


@pytest.fixture(scope="module")
def session(tmp_path_factory: pytest.TempPathFactory) -> RenderSession:
    """Open the sample once with an empty render cache and wait for the images.

    The renderer is built directly (not through `container.build_web_renderer`, which the
    integration conftest replaces with a null renderer): this module is the only place
    that is allowed to start WebEngine, and exactly once per process — see ERRORS.md E-016.
    """
    from mcwr.infrastructure.app_paths import assets_dir
    from mcwr.infrastructure.web_renderer import shared_renderer, views_created

    cache_root = tmp_path_factory.mktemp("render-cache")
    # Same process-wide renderer the other render test module uses: a second hidden view
    # would cost an 11x slowdown (ERRORS.md E-016).
    renderer = shared_renderer(assets_dir(), cache_root)
    window = MainWindow(persist=False, renderer=renderer)
    assert window.open_path(SAMPLE) is True
    assert views_created() <= 1, "one hidden web view per process is the invariant (E-016)"

    app = QApplication.instance()
    assert app is not None
    card_ids = _web_card_ids(window)
    assert len(card_ids) >= 2, "the sample has a math card and a mermaid card"
    _show_and_settle(window)

    started = time.monotonic()
    _drain(app, window, card_ids)
    elapsed = time.monotonic() - started
    rendered = tuple(cid for cid in card_ids if window.card_items[cid].has_image)
    print(f"\ncold render of {len(card_ids)} web cards took {elapsed:.1f}s")
    return RenderSession(window=window, card_ids=card_ids, rendered=rendered, elapsed=elapsed)


@pytest.mark.slow
def test_math_and_mermaid_cards_get_rendered_bodies(session: RenderSession) -> None:
    assert session.rendered == session.card_ids, (
        f"only {len(session.rendered)}/{len(session.card_ids)} math/mermaid cards rendered "
        f"within {RENDER_BUDGET_S:.0f}s; renderer last error: {session.renderer_error}"
    )


@pytest.mark.slow
def test_two_web_cards_do_not_render_the_same_image(session: RenderSession) -> None:
    """Regression guard for the cross-talk: different payloads must give different pixels."""
    digests = set()
    for card_id in session.rendered:
        image = session.window.card_items[card_id]._image  # noqa: SLF001 - comparing pixels
        assert image is not None
        digests.add(hashlib.md5(image.toImage().bits().tobytes()).hexdigest())
    assert len(digests) == len(session.rendered), "two different cards rendered the same image"


@pytest.mark.slow
def test_cold_render_cost_stays_under_the_performance_ceiling(session: RenderSession) -> None:
    """D-022 item 10: the first open must stay usable, and the number must be recorded."""
    assert session.elapsed < PERF_CEILING_S, (
        f"cold render took {session.elapsed:.1f}s, ceiling is {PERF_CEILING_S:.0f}s"
    )


def test_a_failing_renderer_degrades_to_text_without_crashing() -> None:
    """D-022 item 2 (error isolation): no WebEngine involved, so this runs in milliseconds."""

    class FailingRenderer:
        last_error = "injected failure for the isolation test"

        def render(
            self, *, kind: object, source: str, scale: float, theme: str = "light"
        ) -> Path | None:
            del kind, source, scale, theme
            return None

    window = MainWindow(persist=False, renderer=FailingRenderer())  # type: ignore[arg-type]
    assert window.open_path(SAMPLE) is True

    app = QApplication.instance()
    assert app is not None
    for _ in range(20):  # let the render queue run to completion
        app.processEvents()
        time.sleep(0.01)

    assert len(window.card_items) > 0, "the board is still there"
    for card_id in _web_card_ids(window):
        item = window.card_items[card_id]
        assert item.has_image is False, "a failing renderer must not produce an image"
        assert item._document is not None  # noqa: SLF001 - the text fallback is still rendered
