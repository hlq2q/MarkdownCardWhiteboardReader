"""GUI entry point: ``python -m mcwr.interfaces.gui.app [file.md]`` or ``mcwr gui [file.md]``."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication

from mcwr.interfaces.gui.main_window import MainWindow

MODULE_ARGV = ("-m", "mcwr.interfaces.gui.app")


def run(path: Path | None = None, argv: list[str] | None = None) -> int:
    """Start the Qt event loop with one window per process (decision D10)."""
    prepare_webengine()
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    window = MainWindow(path)
    window.show()
    return int(app.exec())


def prepare_webengine() -> bool:
    """Ready QtWebEngine before the QApplication exists (D14).

    QtWebEngine requires the shared-GL-context attribute to be set **before** a
    QGuiApplication is constructed, and its Chromium flags must be in the environment
    before the engine initialises. Import failures (a stripped build, no WebEngine) are
    tolerated: the renderer is then simply unavailable and math/mermaid cards keep their
    text form (FR-1.5).
    """
    from PySide6.QtCore import QCoreApplication, Qt

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    try:
        import mcwr.infrastructure.web_renderer  # noqa: F401  # sets the engine env vars
    except ImportError:  # pragma: no cover - depends on the installed Qt build
        return False
    return True


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
    """Parse arguments and either start the GUI or run the packaged self-check.

    ``--self-check [file.md]`` exists so a **packaged build** can be verified without a
    human at the keyboard: it opens a document (a generated one by default), waits for the
    math/mermaid cards to rasterize, prints a JSON summary and exits non-zero when the
    window or the renderer did not work.
    """
    args = sys.argv[1:] if argv is None else list(argv)
    if args and args[0] == "--self-check":
        target = Path(args[1]) if len(args) > 1 else None
        return run_self_check(target)
    path = Path(args[0]) if args and not args[0].startswith("-") else None
    return run(path)


SELF_CHECK_DOCUMENT = """# Packaged check

Prose that must stay inside a card.

```mermaid
graph TD;
    A[WebEngine] --> B[PNG];
```

$$
\\int_{-\\infty}^{\\infty} e^{-x^2} dx = \\sqrt{\\pi}
$$

| column | value |
| --- | --- |
| cards | 5 |
"""


def run_self_check(path: Path | None = None) -> int:  # pragma: no cover - packaged only
    """Headless-ish smoke test for a frozen build: open, lay out, rasterize, report."""
    import json
    import tempfile
    import time

    from PySide6.QtWidgets import QApplication

    from mcwr.application.features.render_card.service import needs_web_render
    from mcwr.interfaces.gui.main_window import MainWindow

    prepare_webengine()
    app = QApplication.instance() or QApplication(sys.argv)
    document_path = path
    if document_path is None:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8"
        ) as handle:
            handle.write(SELF_CHECK_DOCUMENT)
            document_path = Path(handle.name)

    window = MainWindow(persist=False)
    window.show()
    opened = window.open_path(document_path)

    report: dict[str, object] = {"opened": opened, "document": str(document_path)}
    if opened and window.session.document is not None:
        card_ids = [
            card.card_id
            for card in window.session.document.tree.cards.values()
            if needs_web_render(card) and card.card_id in window.card_items
        ]
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            app.processEvents()
            if all(window.card_items[cid].has_image for cid in card_ids):
                break
            time.sleep(0.05)
        rendered = [cid for cid in card_ids if window.card_items[cid].has_image]
        report |= {
            "cards": len(window.card_items),
            "blocks": len(window.session.document.blocks),
            "web_cards": len(card_ids),
            "rendered_images": len(rendered),
            "renderer_error": getattr(window._renderer, "last_error", None),  # noqa: SLF001
            "renderer_build_error": window.renderer_build_error,
            "frozen": bool(getattr(sys, "frozen", False)),
        }
    report_json = json.dumps(report, ensure_ascii=False)
    # A windowed build has no console, so the report also goes to a file when asked.
    report_path = os.environ.get("MCWR_SELF_CHECK_REPORT", "").strip()
    if report_path:
        Path(report_path).write_text(report_json + "\n", encoding="utf-8")
    print(report_json)
    ok = bool(report.get("opened")) and int(str(report.get("rendered_images", 0))) >= 2
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
