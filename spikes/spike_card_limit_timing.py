"""Timing harness for the card-limit work (T-025 acceptance ②; reused by T-018's stress test).

The integration test (`tests/integration/test_card_limit.py`) asserts the *budget* (≤ 5 s) on
every run; this script prints the actual numbers for a given file set, so the figures quoted
in `TASKS.md` can be reproduced at any time:

    python -m uv run python spikes/spike_card_limit_timing.py file1.md file2.md ...

It builds a window per file with a null renderer (no WebEngine), reports the open time, the
card count, the degraded flag and the item count, then closes the window.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path


class NullRenderer:
    """Same shape as the port; never starts WebEngine (the point is the board, not rasters)."""

    last_error = None

    def render(self, *, kind: object, source: str, scale: float, theme: str = "light") -> None:
        del kind, source, scale, theme


def main(argv: list[str]) -> int:
    from PySide6.QtWidgets import QApplication

    from mcwr.interfaces.gui.app import prepare_webengine
    from mcwr.interfaces.gui.main_window import MainWindow

    if len(argv) < 2:
        print(__doc__)
        return 2

    prepare_webengine()
    app = QApplication.instance() or QApplication([])
    for raw in argv[1:]:
        document = Path(raw)
        window = MainWindow(persist=False, renderer=NullRenderer())  # type: ignore[arg-type]
        started = time.monotonic()
        opened = window.open_path(document)
        elapsed = time.monotonic() - started
        for _ in range(120):
            app.processEvents()
        print(
            f"{document.name}: opened={opened} cards={window.session.card_count} "
            f"over_limit={window.session.over_limit} elapsed={elapsed:.2f}s "
            f"items={len(window.card_items)} zoom={window.view.zoom_percent():.0f}%"
        )
        window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
