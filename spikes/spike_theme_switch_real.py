"""Real-platform theme switch check (not the offscreen test plugin).

Run:  python -m uv run python spikes/spike_theme_switch_real.py
Opens the window, walks 跟随系统 → 深色 → 浅色, reports what changed, exits non-zero if a
switch moved a layout field, changed an item object, or raised inside a slot.

Why this exists on top of `tests/integration/test_theme_switch.py`: the offscreen plugin can
report a different `QStyleHints.colorScheme()` and applies `setStyleSheet` through another
style, so the real `windows` plugin is checked once by hand.
"""

from __future__ import annotations

import json
import sys
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from mcwr.interfaces.gui.main_window import MainWindow
from mcwr.interfaces.gui.theme import ThemeMode

SAMPLE = Path(__file__).resolve().parent / "samples" / "sample.md"
SEEN: list[str] = []


def main() -> int:
    app = QApplication(sys.argv)
    # Qt swallows exceptions raised inside a slot; this hook turns them into a failure.
    sys.excepthook = lambda kind, exc, tb: SEEN.append("".join(traceback.format_exception(kind, exc, tb)))

    window = MainWindow(persist=False)
    window.show()
    opened = window.open_path(SAMPLE)
    window.show()

    report: dict[str, Any] = {
        "platform": app.platformName(),
        "opened": opened,
        "items": len(window.card_items),
    }
    layouts_before = {cid: asdict(layout) for cid, layout in window.session.layouts.items()}
    items_before = window.card_items
    document_before = window.session.document

    steps: list[dict[str, str]] = []
    for mode in (ThemeMode.SYSTEM, ThemeMode.DARK, ThemeMode.LIGHT, ThemeMode.DARK):
        theme = window.apply_theme(mode)
        steps.append(
            {"mode": mode.value, "theme": theme.value, "scene": window.scene.visual_palette.theme.value}
        )
    report["steps"] = steps

    layouts_after = {cid: asdict(layout) for cid, layout in window.session.layouts.items()}
    report["layouts_unchanged"] = layouts_after == layouts_before
    report["items_unchanged"] = window.card_items.keys() == items_before.keys() and all(
        window.card_items[cid] is items_before[cid] for cid in items_before
    )
    report["document_unchanged"] = window.session.document is document_before
    report["slot_exceptions"] = SEEN
    report["ok"] = bool(
        opened
        and report["layouts_unchanged"]
        and report["items_unchanged"]
        and report["document_unchanged"]
        and not SEEN
    )

    QTimer.singleShot(1500, app.quit)
    app.exec()
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
