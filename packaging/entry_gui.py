"""PyInstaller entry point for the packaged GUI (windowed subsystem, decision NFR-7).

Kept as a separate script so the frozen executable has a stable top-level module and the
package itself stays importable for tests and the CLI.
"""

from __future__ import annotations

import multiprocessing
import sys

from mcwr.interfaces.gui.app import main

if __name__ == "__main__":
    # A frozen Qt app that ever spawns a process must freeze-support first (PyInstaller).
    multiprocessing.freeze_support()
    sys.exit(main())
