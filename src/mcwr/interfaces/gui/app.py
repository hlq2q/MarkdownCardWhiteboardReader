"""GUI entry point: ``python -m mcwr.interfaces.gui.app [file.md]`` or ``mcwr gui [file.md]``."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication

from mcwr.interfaces.gui.main_window import MainWindow

MODULE_ARGV = ("-m", "mcwr.interfaces.gui.app")


def run(path: Path | None = None, argv: list[str] | None = None) -> int:
    """Start the Qt event loop with one window per process (decision D10)."""
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    window = MainWindow(path)
    window.show()
    return int(app.exec())


def spawn_new_window(path: Path | None = None, *, parent_pid: int | None = None) -> bool:
    """Start another window in its own process (FR-6.1, decision D10).

    Each process owns its own engine, session id and snapshot shard, which is exactly
    what makes windows independent (FR-6.2). ``parent_pid`` keeps the child alive only
    as long as this window is, so closing the last window does not leave orphans.
    """
    frozen = bool(getattr(sys, "frozen", False))
    program = sys.executable
    arguments = list(MODULE_ARGV) if not frozen else []
    if path is not None:
        arguments.append(str(path))
    if parent_pid is not None:
        arguments += ["--parent-pid", str(parent_pid)]
    ok, _pid = QProcess.startDetached(program, arguments)
    return bool(ok)


def main(argv: list[str] | None = None) -> int:
    """Parse an optional file argument and start the GUI."""
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0]) if args and not args[0].startswith("-") else None
    return run(path)


if __name__ == "__main__":
    raise SystemExit(main())
