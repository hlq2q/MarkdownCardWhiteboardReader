"""T-018 stress test: what a 100 / 500 / 1000 card board actually costs.

Run it on the real platform (fonts, no GPU tricks):

    python -m uv run python spikes/spike_large_document.py                 # fast: no WebEngine
    python -m uv run python spikes/spike_large_document.py --render        # + real KaTeX/Mermaid
    python -m uv run python spikes/spike_large_document.py --rich 30       # 30% rich cards

It prints one line per document and writes the same table to ``spikes/_out/stress_report.md``.
Nothing here asserts: the numbers are the deliverable, and the judgement (does it clear
NFR-2's "open ≤ 3 s / ≥ 30 fps") is written into ``spikes/NOTES.md`` and ``TASKS.md``.

Measured per document:
  parse    read + parse + card tree (pure application layer)
  layout   the board layout slice (pure)
  open     MainWindow.open_path() -> board interactive (items built, fit applied)
  pan/frame  one full-viewport repaint after a pan step (30 steps, average)
  zoom/frame one full-viewport repaint after a zoom step (30 steps, average)
  drag/frame one step of a real card drag (20 steps, average)
  rich     how many math/Mermaid cards the viewport queue holds at fit and at 100 %
  queue    (--render only) wall time until the visible rich cards have images
  mem/GDI/USER   working set and handle counts before/after the board is built
"""

from __future__ import annotations

import argparse
import ctypes
import statistics
import sys
import time
from ctypes import wintypes
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "spikes" / "_out"
TEMP_DIR = Path.home() / "AppData" / "Local" / "Temp" / "mcwr_stress"

REPAINT_STEPS = 30
DRAG_STEPS = 20


# ------------------------------------------------------------------ measurement


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _process_handle() -> int:
    """The current process handle; without argtypes ctypes chokes on the -1 pseudo handle."""
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.GetCurrentProcess.argtypes = []
    return kernel32.GetCurrentProcess()


def _working_set_mb() -> float:
    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    psapi = ctypes.windll.psapi  # type: ignore[attr-defined]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_ProcessMemoryCounters),
        wintypes.DWORD,
    ]
    if not psapi.GetProcessMemoryInfo(_process_handle(), ctypes.byref(counters), counters.cb):
        return float("nan")
    return counters.WorkingSetSize / (1024 * 1024)


def _handle_counts() -> tuple[int, int]:
    """(GDI objects, USER objects) of this process — the classic Windows leak meters.

    Both counters live in ``user32!GetGuiResources`` (0 = GDI, 1 = USER); ``gdi32`` has no
    such entry point.
    """
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    user32.GetGuiResources.restype = wintypes.DWORD
    user32.GetGuiResources.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    process = _process_handle()
    return int(user32.GetGuiResources(process, 0)), int(user32.GetGuiResources(process, 1))


# ------------------------------------------------------------------- documents


def synthesise(cards: int, rich_percent: int, path: Path) -> Path:
    """A document with ``cards`` cards, ``rich_percent`` of them math or mermaid blocks.

    Every heading gets a paragraph, so card counts are predictable: 1 big section + headings
    + one child card per math/mermaid block.
    """
    rich_every = max(100 // max(rich_percent, 1), 1)
    parts: list[str] = []
    rich = 0
    for index in range(cards):
        parts.append(f"# Heading {index}\n\nbody text for card {index}\n")
        if index % rich_every == 0:
            if rich % 2 == 0:
                parts.append(f"$$\nx_{{{index}}}^2 + y_{{{index}}}^2 = z_{{{index}}}^2\n$$\n")
            else:
                parts.append(f"```mermaid\ngraph TD; A{index}-->B{index};\n```\n")
            rich += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts), encoding="utf-8")
    return path


# ------------------------------------------------------------------- measuring


def phases(path: Path) -> tuple[float, float, int, int]:
    """(parse seconds, layout seconds, blocks, cards) using the pure application slices."""
    from mcwr import container
    from mcwr.application.features.layout_board.service import layout_board

    started = time.perf_counter()
    loaded = container.load(path)
    parse_s = time.perf_counter() - started

    started = time.perf_counter()
    layouts = layout_board(
        loaded.tree, blocks=loaded.blocks, estimator=container.build_size_estimator()
    )
    layout_s = time.perf_counter() - started
    return parse_s, layout_s, len(loaded.blocks), len(layouts)


def frame_cost(window, steps: int) -> tuple[float, float, float]:
    """Realistic pan, worst-case full repaint and a zoom step, in median ms.

    * ``pan_small``  — a 16 px scroll step plus a normal repaint cycle: what a wheel tick or a
      mouse-drag pan costs (dirty strip only). This is the number to compare with 30 fps.
    * ``pan_full``   — a large scrollbar jump with a *forced* full-viewport repaint: the worst
      case, and what a fast scrollbar drag degenerates to before Qt coalesces exposure.
    * ``zoom``       — one zoom step plus a normal repaint cycle.
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    assert app is not None
    view = window.view
    bar = view.horizontalScrollBar()
    span = max(bar.maximum() - bar.minimum(), 1)

    bar.setValue(bar.minimum())
    view.viewport().repaint()
    small: list[float] = []
    for index in range(steps):
        started = time.perf_counter()
        bar.setValue(bar.minimum() + 16 * index)
        view.viewport().update()
        app.processEvents()
        small.append((time.perf_counter() - started) * 1000.0)

    step = max(span // steps, 1)
    full: list[float] = []
    for index in range(steps):
        started = time.perf_counter()
        bar.setValue(bar.minimum() + index * step)
        view.viewport().repaint()
        full.append((time.perf_counter() - started) * 1000.0)

    zooms: list[float] = []
    for index in range(steps):
        started = time.perf_counter()
        view.set_zoom(100.0 + (index % 3) * 25.0)
        view.viewport().update()
        app.processEvents()
        zooms.append((time.perf_counter() - started) * 1000.0)
    return statistics.median(small), statistics.median(full), statistics.median(zooms)


def visible_item_count(window) -> int:
    """How many scene items the viewport actually paints (Qt's own culling answer)."""
    view = window.view
    rect = view.mapToScene(view.viewport().rect()).boundingRect()
    return len(view.items(rect))


def repaint_only_cost(window, steps: int = 10) -> float:
    """Median ms for a *bare* full-viewport repaint with nothing changed.

    Separates "the paint itself costs this much" from "the scroll step costs this much": if
    this matches the pan number, the cost is the paint, not the pan.
    """
    view = window.view
    view.viewport().repaint()
    timings: list[float] = []
    for _ in range(steps):
        started = time.perf_counter()
        view.viewport().repaint()
        timings.append((time.perf_counter() - started) * 1000.0)
    return statistics.median(timings)


def drag_cost(window, steps: int) -> float:
    """Median ms per drag step on a real card (the interaction the user feels)."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    window.view.set_zoom(100.0)
    document = window.session.document
    assert document is not None
    heading = next(item for item in window.card_items.values() if item.card.kind.value == "heading")
    window.view.centerOn(heading.sceneBoundingRect().center())
    window.view.viewport().repaint()
    viewport = window.view.viewport()
    centre = viewport.rect().center()
    draggable = heading.mapFromScene(window.view.mapToScene(centre))
    start = QPoint(int(draggable.x()), int(draggable.y()))

    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
    timings: list[float] = []
    for step in range(steps):
        started = time.perf_counter()
        QTest.mouseMove(viewport, start + QPoint(4 * (step + 1), 2 * (step + 1)))
        viewport.repaint()
        timings.append((time.perf_counter() - started) * 1000.0)
    QTest.mouseRelease(
        viewport, Qt.MouseButton.LeftButton, pos=start + QPoint(4 * steps, 2 * steps)
    )
    return statistics.median(timings)


def queue_report(window) -> tuple[int, int]:
    """(rich cards queued at fit zoom, rich cards queued at 100 %) — the T-031 viewport rule."""
    window.view.fit_cards()
    _pump(seconds=0.6)
    window._queue_body_images()
    at_fit = len(window._image_queue)

    window.view.set_zoom(100.0)
    _pump(seconds=0.6)
    window._queue_body_images()
    at_zoom = len(window._image_queue)
    return at_fit, at_zoom


def _pump(seconds: float) -> None:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    assert app is not None
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)


def run_document(path: Path, *, render: bool) -> dict[str, object]:
    from PySide6.QtWidgets import QApplication

    from mcwr.interfaces.gui.main_window import MainWindow

    class CountingRenderer:
        last_error: str | None = None

        def __init__(self) -> None:
            self.calls = 0

        def render(self, *, kind: object, source: str, scale: float, theme: str = "light"):
            del kind, source, scale, theme
            self.calls += 1
            return

    renderer = CountingRenderer()
    window = MainWindow(persist=False, renderer=renderer)  # type: ignore[arg-type]
    window.resize(1400, 900)
    window.show()

    mem_before, (gdi_before, user_before) = _working_set_mb(), _handle_counts()
    started = time.perf_counter()
    opened = window.open_path(path)
    open_s = time.perf_counter() - started
    _pump(seconds=0.3)
    mem_after, (gdi_after, user_after) = _working_set_mb(), _handle_counts()

    parse_s, layout_s, blocks, cards = phases(path)
    pan_ms, zoom_ms = frame_cost(window, REPAINT_STEPS)
    drag_ms = drag_cost(window, DRAG_STEPS)
    at_fit, at_zoom = queue_report(window)

    queue_s = float("nan")
    if render:
        from mcwr.infrastructure.app_paths import assets_dir
        from mcwr.infrastructure.web_renderer import shared_renderer

        window._renderer = shared_renderer(assets_dir(), TEMP_DIR / "render-cache")  # noqa: SLF001
        window.view.set_zoom(100.0)
        started = time.perf_counter()
        _pump(seconds=0.6)
        window._queue_body_images()
        target = len(window._image_queue)
        deadline = time.monotonic() + 300.0
        while time.monotonic() < deadline and any(
            item.is_pending for item in window.card_items.values()
        ):
            QApplication.instance().processEvents()  # type: ignore[union-attr]
            time.sleep(0.02)
        queue_s = time.perf_counter() - started
        window._queue_body_images()
        at_zoom = max(at_zoom, target)

    return {
        "file": path.name,
        "cards": len(window.card_items),
        "blocks": blocks,
        "layout_cards": cards,
        "parse_s": parse_s,
        "layout_s": layout_s,
        "open_s": open_s,
        "pan_ms": pan_ms,
        "zoom_ms": zoom_ms,
        "drag_ms": drag_ms,
        "rich_fit": at_fit,
        "rich_100": at_zoom,
        "queue_s": queue_s,
        "renders": renderer.calls,
        "mem_mb": mem_after - mem_before,
        "gdi": gdi_after - gdi_before,
        "user": user_after - user_before,
        "opened": opened,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cards", type=int, nargs="*", default=[100, 500, 1000])
    parser.add_argument("--rich", type=int, default=10, help="percent of cards with math/mermaid")
    parser.add_argument("--render", action="store_true", help="also time real KaTeX/Mermaid")
    parser.add_argument("--reuse", action="store_true", help="reuse the generated documents")
    args = parser.parse_args()

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    rows: list[dict[str, object]] = []
    for cards in args.cards:
        path = TEMP_DIR / f"stress_{cards}_{args.rich}pct.md"
        if not (args.reuse and path.is_file()):
            synthesise(cards, args.rich, path)
        row = run_document(path, render=args.render)
        rows.append(row)
        print(
            f"{row['file']}: cards={row['cards']} blocks={row['blocks']} "
            f"parse={row['parse_s']:.2f}s layout={row['layout_s']:.2f}s "
            f"open={row['open_s']:.2f}s pan={row['pan_ms']:.1f}ms zoom={row['zoom_ms']:.1f}ms "
            f"drag={row['drag_ms']:.1f}ms rich_fit={row['rich_fit']} rich_100={row['rich_100']} "
            f"queue={row['queue_s']:.1f}s renders={row['renders']} "
            f"mem=+{row['mem_mb']:.0f}MB gdi=+{row['gdi']} user=+{row['user']}",
            flush=True,
        )
        del app

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = OUT_DIR / "stress_report.md"
    header = (
        "| 文档 | 卡片 | 块 | parse | layout | open | pan16/帧 | pan全屏/帧 | 纯重绘/帧 | 可见item | "
        "zoom/帧 | drag/帧 | 视口内 rich(fit/100%) | 队列 | 渲染调用 | 内存增量(总) | GDI/USER |\n"
        + "| --- " * 18
        + "|\n"
    )
    lines = [
        f"| {row['file']} | {row['cards']} | {row['blocks']} | {row['parse_s']:.2f}s | "
        f"{row['layout_s']:.2f}s | {row['open_s']:.2f}s | {row['pan_ms']:.1f}ms | "
        f"{row['zoom_ms']:.1f}ms | {row['drag_ms']:.1f}ms | {row['rich_fit']}/{row['rich_100']} | "
        f"{row['queue_s']:.1f}s | {row['renders']} | +{row['mem_mb']:.0f}MB | "
        f"+{row['gdi']}/+{row['user']} |"
        for row in rows
    ]
    report.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
