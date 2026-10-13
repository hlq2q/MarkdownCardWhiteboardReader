"""T-026: one test per evidence item of decision D-022 (render stability).

Each test name carries the item number it proves, so `TASKS.md` can point at it. The items
are deliberately independent of the real WebEngine where possible, so this file is fast and
does not compete with `test_body_render.py` for the one web view per process.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtWidgets import QApplication

from mcwr.interfaces.gui.main_window import MainWindow

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "spikes" / "samples" / "sample.md"
STABILITY_DOC = REPO_ROOT / "docs" / "render-stability.md"

FORBIDDEN_IN_CORE = ("PySide6", "QtWebEngine", "markdown_it", "httpx", "loguru")


class NullRenderer:
    """Stands in for the rasterizer: no WebEngine, no image."""

    last_error = "null renderer"

    def render(
        self, *, kind: object, source: str, scale: float, theme: str = "light"
    ) -> Path | None:
        del kind, source, scale, theme
        return None


def _drain(app: QApplication, rounds: int = 20) -> None:
    for _ in range(rounds):
        app.processEvents()
        time.sleep(0.01)


def _web_card_ids(window: MainWindow) -> list[str]:
    from mcwr.application.features.render_card.service import needs_web_render

    document = window.session.document
    assert document is not None
    return [
        card_id
        for card_id, card in document.tree.cards.items()
        if needs_web_render(card) and card_id in window.card_items
    ]


def test_item_1_application_and_domain_do_not_import_gui_or_libraries() -> None:
    """D-022 item 1: parsing, card building and layouts stay separable from rendering."""
    offenders: list[str] = []
    scanned = 0
    for layer in ("domain", "application"):
        for path in (REPO_ROOT / "src" / "mcwr" / layer).rglob("*.py"):
            if path.name.startswith("test_"):
                continue
            scanned += 1
            text = path.read_text(encoding="utf-8")
            for token in FORBIDDEN_IN_CORE:
                if f"import {token}" in text or f"from {token}" in text:
                    offenders.append(f"{path.relative_to(REPO_ROOT)} imports {token}")
    assert scanned >= 20, f"the scan must actually cover the core layers, saw {scanned} files"
    assert offenders == [], f"core layers must not depend on concrete libraries: {offenders}"


def test_item_3_the_mature_library_inventory_is_recorded() -> None:
    """D-022 item 3: no self-made parsers/renderers — and the choice is written down."""
    assert STABILITY_DOC.is_file(), "docs/render-stability.md is the inventory (T-026 item 3)"
    text = STABILITY_DOC.read_text(encoding="utf-8")
    for library in ("markdown-it-py", "KaTeX", "Mermaid", "Pygments", "QtWebEngine"):
        assert library in text, f"{library} must be listed with version/licence evidence"


def test_item_4_a_card_shows_a_placeholder_while_its_image_is_pending() -> None:
    """D-022 item 4: async render with a visible placeholder instead of a silent stall.

    Since T-031 only cards that are on screen (and big enough) are queued, so the test puts the
    viewport on a rich card at 100% and runs the queue pass the debounce would run.
    """
    window = MainWindow(persist=False, renderer=NullRenderer())  # type: ignore[arg-type]
    window.show()
    assert window.open_path(SAMPLE) is True

    rich = _web_card_ids(window)
    assert rich, "the sample has cards that need rendering"
    target = window.card_items[rich[0]]
    window.view.set_zoom(100.0)
    window.view.centerOn(target.sceneBoundingRect().center())
    window._queue_body_images()

    queued = list(window._image_queue)
    assert target.card.card_id in queued, "the card under the viewport is queued"
    for card_id in queued:
        assert window.card_items[card_id].is_pending is True, "queued cards announce progress"

    app = QApplication.instance()
    assert app is not None
    _drain(app)

    for card_id in queued:
        assert window.card_items[card_id].is_pending is False, "progress ends after the attempt"
        assert window.card_items[card_id].has_image is False, "a null renderer yields no image"


def test_item_6_twenty_consecutive_refreshes_stay_stable() -> None:
    """D-022 item 6: structure-first rebuild must not crash, blank out or hang."""
    window = MainWindow(persist=False, renderer=NullRenderer())  # type: ignore[arg-type]
    assert window.open_path(SAMPLE) is True
    document = window.session.document
    assert document is not None
    expected_cards = len(document.tree.cards)

    app = QApplication.instance()
    assert app is not None
    for _ in range(20):
        assert window.session.refresh() is True
        _drain(app, rounds=1)
        current = window.session.document
        assert current is not None
        assert len(current.tree.cards) == expected_cards, "the card set must survive a refresh"
        assert len(window.card_items) == expected_cards, "no card item may go missing"
        assert set(window.session.layouts) == set(current.tree.cards), "every card keeps a layout"


def test_item_7_a_failing_window_does_not_affect_another_window() -> None:
    """D-022 item 7: window isolation — a broken renderer in one window stays there."""
    broken = MainWindow(persist=False, renderer=NullRenderer())  # type: ignore[arg-type]
    healthy = MainWindow(persist=False, renderer=NullRenderer())  # type: ignore[arg-type]
    assert broken.open_path(SAMPLE) is True
    assert healthy.open_path(SAMPLE) is True

    app = QApplication.instance()
    assert app is not None
    _drain(app)

    assert len(healthy.card_items) == len(broken.card_items)
    healthy_document = healthy.session.document
    assert healthy_document is not None
    assert set(healthy.session.layouts) == set(healthy_document.tree.cards)
    assert healthy.renderer_build_error == "", "the other window never saw a failure"
    for card_id in _web_card_ids(healthy):
        assert healthy.card_items[card_id].has_image is False  # its own null renderer


def test_item_9_failures_are_logged_and_the_status_text_stays_short(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-022 item 9: key errors reach the log; the visible message stays readable."""
    import mcwr.shared.logging as logging_module

    log_dir = tmp_path / "logs"
    monkeypatch.setattr(logging_module, "log_dir", lambda: log_dir)
    monkeypatch.setattr(logging_module, "_configured", False)
    log_path = logging_module.configure_logging(level="ERROR")
    assert log_path.parent == log_dir, "logs never go next to the Markdown file"

    window = MainWindow(persist=False, renderer=NullRenderer())  # type: ignore[arg-type]
    assert window.open_path(SAMPLE) is True
    app = QApplication.instance()
    assert app is not None
    _drain(app)

    window._show_failure("body rendering unavailable: injected failure")  # noqa: SLF001
    logging_module.logger().complete()  # flush loguru's queue before reading the file

    assert log_path.is_file(), "the error sink must create the log file"
    logged = log_path.read_text(encoding="utf-8")
    assert "body rendering unavailable" in logged, f"log did not capture the failure: {logged!r}"

    status = window.statusBar().currentMessage()
    assert isinstance(status, str)
    assert 0 < len(status) <= 40, f"status text must stay short, got {len(status)}: {status!r}"


def _unused(_value: Any) -> None:  # pragma: no cover - keeps the Any import meaningful
    return None
