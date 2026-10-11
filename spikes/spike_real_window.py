"""Manual check on the real Windows platform plugin (not the offscreen test plugin).

Run:  python -m uv run python spikes/spike_real_window.py
Opens the window for ~1.5 s, prints what it built, and exits.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from mcwr.interfaces.gui.main_window import MainWindow

SAMPLE = Path(__file__).resolve().parent / "samples" / "sample.md"


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow(persist=False)
    window.show()
    opened = window.open_path(SAMPLE)
    window.show()  # raise again after the fit so the window is really on screen
    QTimer.singleShot(1500, app.quit)
    code = int(app.exec())
    print(f"platform={app.platformName()} opened={opened} visible={window.isVisible()}")
    print(f"items={len(window.card_items)} zoom={window.view.zoom_percent():.0f}%")
    print(f"scene_rect={window.scene.itemsBoundingRect()}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
