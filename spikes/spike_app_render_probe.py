"""Repro through the real window path: which source and which image does each card get?

Run:  python -m uv run python spikes/spike_app_render_probe.py
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

from mcwr.application.features.render_card.service import (  # noqa: E402
    needs_web_render,
    web_source,
)
from mcwr.interfaces.gui.main_window import MainWindow  # noqa: E402

SAMPLE = Path(__file__).resolve().parent / "samples" / "sample.md"
OUT = Path(__file__).resolve().parent / "_out"


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow(persist=False)
    assert window.open_path(SAMPLE)

    document = window.session.document
    assert document is not None
    blocks = window.session.blocks
    web_cards = [
        card
        for card in document.tree.cards.values()
        if needs_web_render(card) and card.card_id in window.card_items
    ]
    print(f"web cards in document order: {[(c.kind.value, c.title) for c in web_cards]}")

    deadline = time.monotonic() + 45
    ticker = QTimer()
    ticker.setInterval(50)
    results: list[bool] = []

    def check() -> None:
        done = all(window.card_items[c.card_id].has_image for c in web_cards)
        if done or time.monotonic() > deadline:
            results.append(done)
            app.quit()

    ticker.timeout.connect(check)
    ticker.start()
    app.exec()  # a real event loop, not hand-driven processEvents()
    app.processEvents()

    OUT.mkdir(exist_ok=True)
    for card in web_cards:
        item = window.card_items[card.card_id]
        source = web_source(card, blocks, card.block_index if card.block_index else -1) or ""
        print(f"--- {card.kind.value} block={card.block_index} has_image={item.has_image}")
        print(f"    source: {source[:60]!r}")
        if item.has_image and item._image is not None:  # noqa: SLF001 - probe
            from PySide6.QtCore import QBuffer, QIODevice

            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            item._image.save(buffer, "PNG")  # noqa: SLF001
            payload = bytes(buffer.data())
            digest = hashlib.md5(payload).hexdigest()[:12]
            target = OUT / f"probe_{card.kind.value}.png"
            target.write_bytes(payload)
            print(
                f"    item image: {item._image.width()}x{item._image.height()} md5={digest} -> {target}"
            )

    renderer = window._renderer  # noqa: SLF001
    if renderer is not None:
        print("--- direct render, outside any timer callback ---")
        direct = renderer.render(kind=web_cards[0].kind, source="graph TD; X-->Y;", scale=1.0)
        print(f"direct render: {direct} error={renderer.last_error}")
        print(f"renderer failures: {getattr(renderer, 'failures', None)}")
        print(f"renderer last_error: {getattr(renderer, 'last_error', None)}")
        print(f"renderer stats: {getattr(renderer, 'stats', None)}")
        view = getattr(renderer, "_view", None)
        if view is not None:
            page = view.page()
            print(f"page url: {page.url().toString()}")
            print(f"view size: {view.width()}x{view.height()} visible={view.isVisible()}")
            answer: list[object] = []
            page.runJavaScript(
                "JSON.stringify([typeof window.mcwrRender, window.mcwrState, "
                "window.mcwrRenders, document.readyState, location.href])",
                lambda value: answer.append(value),
            )
            deadline = time.monotonic() + 5
            while not answer and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.02)
            print(f"page state: {answer[0] if answer else 'no answer'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
