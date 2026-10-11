"""GUI entry point: ``python -m mcwr.interfaces.gui.app [file.md]`` or ``mcwr gui [file.md]``."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from mcwr.interfaces.gui.main_window import MainWindow


def run(path: Path | None = None, argv: list[str] | None = None) -> int:
    """Start the Qt event loop with one window per process (decision D10)."""
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    window = MainWindow(path)
    window.show()
    return int(app.exec())


def main(argv: list[str] | None = None) -> int:
    """Parse an optional file argument and start the GUI."""
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0]) if args else None
    return run(path)


if __name__ == "__main__":
    raise SystemExit(main())
