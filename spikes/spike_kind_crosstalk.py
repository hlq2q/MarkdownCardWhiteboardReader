"""Repro: does one renderer instance return different images for different payload kinds?

Run:  python -m uv run python spikes/spike_kind_crosstalk.py
Writes both rasters to spikes/_out/ for eyeballing.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

from mcwr.domain.enums import CardKind  # noqa: E402
from mcwr.infrastructure.app_paths import assets_dir  # noqa: E402
from mcwr.infrastructure.web_renderer import QtWebCardRenderer  # noqa: E402

FORMULA = r"e^{i\pi} + 1 = 0"
DIAGRAM = "graph TD;\n    A[Start] --> B{Choice};\n    B -->|yes| C[Done];"

OUT = Path(__file__).resolve().parent / "_out"


def digest(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()[:12]


def main() -> int:
    app = QApplication(sys.argv)
    cache = Path(os.environ.get("TEMP", ".")) / "mcwr_kind_probe"
    renderer = QtWebCardRenderer(assets_dir(), cache)
    math_path = renderer.render(kind=CardKind.MATH_BLOCK, source=FORMULA, scale=1.0)
    mermaid_path = renderer.render(kind=CardKind.MERMAID, source=DIAGRAM, scale=1.0)
    print(f"math   : {math_path} error={renderer.last_error}")
    print(f"mermaid: {mermaid_path} error={renderer.last_error}")
    if math_path is None or mermaid_path is None:
        print("RESULT: a render failed")
        return 1
    print(f"md5 math={digest(math_path)} mermaid={digest(mermaid_path)}")
    same = digest(math_path) == digest(mermaid_path)
    print(f"RESULT: {'IDENTICAL (cross-talk!)' if same else 'different images (ok)'}")
    OUT.mkdir(exist_ok=True)
    import shutil

    shutil.copyfile(math_path, OUT / "kind_probe_math.png")
    shutil.copyfile(mermaid_path, OUT / "kind_probe_mermaid.png")
    return 1 if same else 0


if __name__ == "__main__":
    raise SystemExit(main())
