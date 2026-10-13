"""Spike 3 (D14 / R2): can KaTeX + Mermaid render to an image *offscreen* via QtWebEngine?

Question: the whiteboard is scaled by one canvas transform (D7), so live WebViews are
unusable.  D14 says: use WebEngine only as an *offscreen rasterizer*, cache PNGs by
`content_hash` + scale bucket.  This spike checks that the rasterizer actually works on
this machine, how fast it is, how crisp it gets, and what it costs in memory.

Run:  python -m uv run python spikes/spike_web_render.py
      python -m uv run python spikes/spike_web_render.py --fetch-assets   # download KaTeX/Mermaid
      python -m uv run python spikes/spike_web_render.py --worker <mode>  # internal (child process)

Exit code 0 means: at least one render strategy produced PNGs.  The harness spawns one
child process per (strategy x environment) combination, because the Chromium switches and
QT_QPA_PLATFORM must be in the environment *before* QtWebEngineCore is initialised.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "mcwr" / "assets" / "web"
OUT = Path(__file__).resolve().parent / "_out"

# Pinned versions (npm, MIT).  Recorded in src/mcwr/assets/web/LICENSES.md.
KATEX_VERSION = "0.19.0"
MERMAID_VERSION = "12.1.0"

SHELL_HTML = """<!doctype html>
<html><head><meta charset="utf-8">
<link rel="stylesheet" href="{katex_css}">
<style>
  html, body {{ margin:0; padding:0; background:#ffffff; }}
  #stage {{ display:block; width:{stage_width}px; padding:8px; background:#ffffff;
            box-sizing:content-box; }}
  .katex-display {{ margin:0.4em 0; }}
  .katex {{ font-size:20px; }}
  #stage svg {{ max-width:none; }}
</style>
</head><body><div id="stage"></div>
<script src="{katex_js}"></script>
<script src="{mermaid_js}"></script>
<script>
window.mcwrState = "boot";
window.mcwrError = null;
window.mcwrSize = {{w: 0, h: 0}};
let seq = 0;

function measure() {{
  const r = document.getElementById("stage").getBoundingClientRect();
  window.mcwrSize = {{w: Math.ceil(r.width), h: Math.ceil(r.height)}};
}}

window.mcwrRender = function (kind, payload) {{
  window.mcwrState = "busy";
  window.mcwrError = null;
  const stage = document.getElementById("stage");
  try {{
    if (kind === "math") {{
      stage.innerHTML = "";
      const box = document.createElement("div");
      katex.render(payload, box, {{displayMode: true, throwOnError: false}});
      stage.appendChild(box);
      measure(); window.mcwrState = "done";
      return Promise.resolve(window.mcwrSize);
    }}
    if (kind === "mermaid") {{
      return mermaid.render("mmd" + (++seq), payload).then(function (res) {{
        stage.innerHTML = res.svg;
        const svg = stage.querySelector("svg");
        if (svg) {{
          svg.removeAttribute("height");
          svg.style.width = "100%";
          svg.style.height = "auto";
          svg.style.maxWidth = "none";
        }}
        measure(); window.mcwrState = "done";
        return window.mcwrSize;
      }}).catch(function (e) {{
        window.mcwrError = String(e); window.mcwrState = "error"; return null;
      }});
    }}
    throw new Error("unknown kind " + kind);
  }} catch (e) {{
    window.mcwrError = String(e && e.stack || e); window.mcwrState = "error";
    return Promise.resolve(null);
  }}
}};

mermaid.initialize({{startOnLoad: false, theme: "neutral", securityLevel: "loose"}});
window.mcwrState = "ready";
</script>
</body></html>
"""

STAGE_WIDTH = 480  # px: representative card-body width on the whiteboard

SAMPLES: dict[str, tuple[str, str]] = {
    # name: (kind, payload)
    "math_block": (
        "math",
        r"e^{i\pi}+1=0 \qquad \int_{-\infty}^{\infty} e^{-x^{2}}\,dx=\sqrt{\pi}"
        r" \qquad \frac{\partial^{2}u}{\partial t^{2}}=c^{2}\nabla^{2}u",
    ),
    "math_block2": ("math", r"\sum_{k=1}^{n} \frac{1}{k^{2}} = \frac{\pi^{2}}{6}"),
    "mermaid_flow": (
        "mermaid",
        "graph TD\n"
        "  A[Markdown file] --> B{Block kind?}\n"
        "  B -->|math| C[KaTeX offscreen]\n"
        "  B -->|mermaid| D[Mermaid offscreen]\n"
        "  C --> E[(PNG cache)]\n"
        "  D --> E\n"
        "  E --> F[Whiteboard image item]",
    ),
}

BUCKETS = [1.0, 1.5, 2.0]


# --------------------------------------------------------------------------- assets


def fetch_assets() -> int:
    """Download the *minimal* KaTeX + Mermaid distributions from the npm registry."""
    import io
    import tarfile
    import urllib.request

    ASSETS.mkdir(parents=True, exist_ok=True)
    plan = [
        (
            "katex",
            KATEX_VERSION,
            lambda n: (
                n == "package/dist/katex.min.js"
                or n == "package/dist/katex.min.css"
                or (n.startswith("package/dist/fonts/") and n.endswith(".woff2"))
                or n == "package/LICENSE"
            ),
        ),
        (
            "mermaid",
            MERMAID_VERSION,
            lambda n: n in ("package/dist/mermaid.min.js", "package/LICENSE"),
        ),
    ]
    written: list[str] = []
    for name, version, keep in plan:
        url = f"https://registry.npmjs.org/{name}/-/{name}-{version}.tgz"
        dest = ASSETS / name
        dest.mkdir(parents=True, exist_ok=True)
        print(f"[fetch] {url}")
        try:
            with urllib.request.urlopen(url, timeout=90) as resp:  # noqa: S310 (spike)
                blob = resp.read()
        except Exception as exc:  # pragma: no cover - network blocker path
            print(f"[fetch] FAILED {url}: {exc!r}")
            return 2
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
            for member in tf.getmembers():
                if not member.isfile() or not keep(member.name):
                    continue
                rel = member.name[len("package/") :]
                if rel == "LICENSE":
                    rel = "LICENSE.txt"
                if name == "katex" and rel.startswith("dist/"):
                    rel = rel[len("dist/") :]
                target = dest / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                data = tf.extractfile(member)
                assert data is not None
                target.write_bytes(data.read())
                written.append(str(target.relative_to(ROOT)))
    # Strip the woff/ttf fallbacks from katex.min.css: Chromium uses woff2 only, and this
    # keeps the shipped asset set small (fonts are ~40% of the tarball otherwise).
    css = ASSETS / "katex" / "katex.min.css"
    if css.is_file():
        text = css.read_text(encoding="utf-8")
        import re

        text = re.sub(r",url\(fonts/[^)]+\.(?:woff|ttf)\)[^,}]*", "", text)
        css.write_text(text, encoding="utf-8")
    for path in written:
        print(f"[fetch] wrote {path}")
    print(f"[fetch] done: {len(written)} files")
    return 0


# --------------------------------------------------------------------------- memory (ctypes)


class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD),
        ("PageFaultCount", wt.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("cntUsage", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD),
        ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wt.DWORD),
        ("szExeFile", wt.WCHAR * 260),
    ]


def _mem_for(pid: int) -> tuple[int, int] | None:
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        counters = _PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        if not k32.K32GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return None
        return int(counters.WorkingSetSize), int(counters.PeakWorkingSetSize)
    finally:
        k32.CloseHandle(handle)


def mem_report(label: str) -> dict[str, object]:
    """Working set of this process + every QtWebEngineProcess.exe (sum + peak)."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    TH32CS_SNAPPROCESS = 0x00000002
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    own = os.getpid()
    total_ws = 0
    total_peak = 0
    procs: dict[str, object] = {}
    if snap and snap != ctypes.c_void_p(-1).value:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            name = entry.szExeFile
            pid = int(entry.th32ProcessID)
            if pid == own or name.lower() == "qtwebengineprocess.exe":
                info = _mem_for(pid)
                if info:
                    ws, peak = info
                    key = "self" if pid == own else f"{name}:{pid}"
                    procs[key] = {
                        "working_set_mb": round(ws / 2**20, 1),
                        "peak_mb": round(peak / 2**20, 1),
                    }
                    total_ws += ws
                    total_peak += peak
            ok = k32.Process32NextW(snap, ctypes.byref(entry))
        k32.CloseHandle(snap)
    result = {
        "label": label,
        "procs": procs,
        "total_working_set_mb": round(total_ws / 2**20, 1),
        "total_peak_mb": round(total_peak / 2**20, 1),
    }
    print(
        f"[mem] {label}: total_ws={result['total_working_set_mb']}MB "
        f"total_peak={result['total_peak_mb']}MB {procs}"
    )
    return result


# --------------------------------------------------------------------------- worker (child)


def _shell_path() -> Path:
    return OUT / "_shell.html"


def write_shell() -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    katex = ASSETS / "katex"
    html = SHELL_HTML.format(
        katex_css=(katex / "katex.min.css").as_uri(),
        katex_js=(katex / "katex.min.js").as_uri(),
        mermaid_js=(ASSETS / "mermaid" / "dist" / "mermaid.min.js").as_uri(),
        stage_width=STAGE_WIDTH,
    )
    path = _shell_path()
    path.write_text(html, encoding="utf-8")
    return path


def worker(mode: str) -> int:
    """Child process: one strategy, one environment (already set by the parent)."""
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    os.environ.setdefault(
        "QTWEBENGINE_CHROMIUM_FLAGS",
        "--disable-gpu --no-sandbox --disable-features=AudioServiceOutOfProcess",
    )
    from PySide6.QtCore import QEventLoop, QMarginsF, QSize, QSizeF, QTimer, QUrl
    from PySide6.QtGui import QImage, QPageLayout, QPageSize
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
    from PySide6.QtWidgets import QApplication

    result: dict[str, object] = {"mode": mode, "qt": None, "strategy": mode}
    timings: dict[str, float] = {}
    t_start = time.perf_counter()
    app = QApplication(sys.argv[:1])
    result["platform"] = app.platformName()
    result["chromium_flags"] = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    result["qt_qpa_platform_env"] = os.environ.get("QT_QPA_PLATFORM", "")

    def pump(ms: int = 60) -> None:
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def grab_settled(view, max_ms: int = 3000, quiet_ms: int = 60, stable_needed: int = 3):
        """grab() until N consecutive frames are byte-identical (WebEngine paints async).

        Returns (QImage, settle_ms, grabs).  A stale frame after resize()/setZoomFactor()
        is exactly the failure this guards against: two identical frames can still be a
        half-composited frame, so three are required.
        """
        import hashlib

        t0 = time.perf_counter()
        prev = None
        same = 0
        grabs = 0
        img = None
        while (time.perf_counter() - t0) * 1000 < max_ms:
            pump(quiet_ms)
            img = view.grab().toImage()
            grabs += 1
            digest = hashlib.sha1(bytes(img.constBits())).hexdigest()
            same = same + 1 if digest == prev else 1
            prev = digest
            if same >= stable_needed:
                return img, round((time.perf_counter() - t0) * 1000, 1), grabs
        return img, round((time.perf_counter() - t0) * 1000, 1), grabs

    def wait_js(page: QWebEnginePage, expr: str, timeout_s: float = 30.0):
        """Poll runJavaScript(expr) until it is truthy; returns (value, seconds)."""
        box: dict[str, object] = {}
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < timeout_s:
            done = {"ok": False}

            def cb(value, _done=done, _box=box):  # noqa: ANN001
                _box["value"] = value
                _done["ok"] = True

            page.runJavaScript(expr, cb)
            while not done["ok"] and time.perf_counter() - t0 < timeout_s:
                pump(20)
            if done["ok"] and box.get("value"):
                return box["value"], time.perf_counter() - t0
            if done["ok"] and box.get("value") is False and expr.startswith("window.mcwrState"):
                pass
        return None, time.perf_counter() - t0

    def wait_state(page: QWebEnginePage, timeout_s: float = 30.0) -> tuple[str, float]:
        value, secs = wait_js(
            page,
            "window.mcwrState === 'done' ? 'done' : "
            "(window.mcwrState === 'error' ? ('error:' + window.mcwrError) "
            ": (window.mcwrState === 'ready' ? 'ready' : false))",
            timeout_s,
        )
        return str(value), secs

    def read_size(page: QWebEnginePage, timeout_s: float = 10.0) -> tuple[int, int, object]:
        """Content box in CSS px, read back as a JSON string (objects are unreliable)."""
        value, _ = wait_js(
            page, "JSON.stringify([window.mcwrSize.w, window.mcwrSize.h])", timeout_s
        )
        try:
            w, h = json.loads(str(value))
            return int(w), int(h), value
        except Exception:
            return 0, 0, value

    shell = write_shell()
    base = QUrl.fromLocalFile(str(OUT) + os.sep)

    # ---------------------------------------------------------------- strategy: view grab
    if mode in ("view-window", "view-offscreen", "view-reuse"):
        from PySide6.QtWebEngineWidgets import QWebEngineView

        view = QWebEngineView()
        view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )
        view.resize(1200, 800)
        from PySide6.QtCore import Qt

        # WA_DontShowOnScreen keeps the real "windows" platform plugin but never puts a
        # window on the desktop; the "offscreen" platform plugin has no real window at all.
        view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, mode != "view-offscreen")
        view.show()
        page = view.page()
        loaded = {"ok": False, "err": None}
        page.loadFinished.connect(lambda ok: loaded.update(ok=ok))
        page.load(QUrl.fromLocalFile(str(shell)))
        t0 = time.perf_counter()
        while not loaded["ok"] and time.perf_counter() - t0 < 40:
            pump(50)
            if loaded["err"] is not None:
                break
        if not loaded["ok"]:
            raise RuntimeError(f"shell page never finished loading (platform={app.platformName()})")
        state, _ = wait_state(page, 15)
        timings["cold_start_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
        if state != "ready":
            raise RuntimeError(f"shell script not ready: {state}")
        result["shell_ready"] = True

        renders: list[dict[str, object]] = []
        for name, (kind, payload) in SAMPLES.items():
            for zoom in BUCKETS:
                if "view-reuse" in mode and zoom != 1.0 and name != "math_block":
                    continue
                t_js = time.perf_counter()
                page.runJavaScript(f"window.mcwrRender({json.dumps(kind)}, {json.dumps(payload)})")
                state, _ = wait_state(page, 30)
                js_ms = round((time.perf_counter() - t_js) * 1000, 1)
                if state != "done":
                    renders.append({"name": name, "zoom": zoom, "error": state})
                    continue
                css_w, css_h, raw_size = read_size(page)
                if not css_w or not css_h:
                    renders.append(
                        {"name": name, "zoom": zoom, "error": f"size readback {raw_size!r}"}
                    )
                    continue
                t_lay = time.perf_counter()
                page.setZoomFactor(zoom)
                view.resize(int(round(css_w * zoom)) + 2, int(round(css_h * zoom)) + 2)
                pump(30)
                layout_ms = round((time.perf_counter() - t_lay) * 1000, 1)
                t_grab = time.perf_counter()
                img, settle_ms, grabs = grab_settled(view)
                png = OUT / f"{name}_{mode}_z{zoom}.png"
                img.save(str(png))
                grab_ms = round((time.perf_counter() - t_grab) * 1000, 1)
                renders.append(
                    {
                        "name": name,
                        "kind": kind,
                        "zoom": zoom,
                        "css_size": [css_w, css_h],
                        "png": str(png.relative_to(ROOT)),
                        "png_size": [img.width(), img.height()],
                        "render_ms": js_ms,
                        "layout_settle_ms": layout_ms,
                        "paint_settle_ms": settle_ms,
                        "grabs": grabs,
                        "grab_save_ms": grab_ms,
                        "ms": round(js_ms + layout_ms + grab_ms, 1),
                    }
                )
        result["renders"] = renders
        result["memory"] = mem_report(f"{mode} after renders")

    # ---------------------------------------------------------------- strategy: printToPdf
    elif mode in ("pdf-window", "pdf-offscreen"):
        from PySide6.QtPdf import QPdfDocument

        page = QWebEnginePage()
        page.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )
        page.settings().setAttribute(QWebEngineSettings.WebAttribute.PrintElementBackgrounds, True)
        loaded = {"ok": False}
        page.loadFinished.connect(lambda ok: loaded.update(ok=ok))
        page.load(QUrl.fromLocalFile(str(shell)))
        t0 = time.perf_counter()
        while not loaded["ok"] and time.perf_counter() - t0 < 40:
            pump(50)
        if not loaded["ok"]:
            raise RuntimeError("shell page never finished loading (page-only strategy)")
        state, _ = wait_state(page, 15)
        if state != "ready":
            raise RuntimeError(f"shell script not ready: {state}")
        timings["cold_start_ms"] = round((time.perf_counter() - t_start) * 1000, 1)

        renders = []
        for name, (kind, payload) in SAMPLES.items():
            t_r = time.perf_counter()
            page.runJavaScript(f"window.mcwrRender({json.dumps(kind)}, {json.dumps(payload)})")
            state, _ = wait_state(page, 30)
            if state != "done":
                renders.append({"name": name, "error": state})
                continue
            css_w, css_h, raw_size = read_size(page)
            if not css_w or not css_h:
                renders.append({"name": name, "error": f"size readback {raw_size!r}"})
                continue
            pdf = OUT / f"{name}_{mode}.pdf"
            layout = QPageLayout(
                QPageSize(QSizeF(css_w * 0.75, css_h * 0.75), QPageSize.Unit.Point, "card"),
                QPageLayout.Orientation.Portrait,
                QMarginsF(0, 0, 0, 0),
            )
            finished = {"ok": False}
            page.pdfPrintingFinished.connect(lambda path, ok: finished.update(ok=ok, path=path))
            page.printToPdf(str(pdf), layout)
            t0 = time.perf_counter()
            while not finished["ok"] and time.perf_counter() - t0 < 40:
                pump(50)
            pdf_ms = round((time.perf_counter() - t_r) * 1000, 1)
            doc = QPdfDocument()
            doc.load(str(pdf))
            buckets = []
            for scale in BUCKETS:
                t_b = time.perf_counter()
                img: QImage = doc.render(0, QSize(int(css_w * scale), int(css_h * scale)))
                png = OUT / f"{name}_{mode}_z{scale}.png"
                img.save(str(png))
                buckets.append(
                    {
                        "scale": scale,
                        "png": str(png.relative_to(ROOT)),
                        "png_size": [img.width(), img.height()],
                        "raster_ms": round((time.perf_counter() - t_b) * 1000, 1),
                    }
                )
            renders.append(
                {
                    "name": name,
                    "kind": kind,
                    "css_size": [css_w, css_h],
                    "pdf": str(pdf.relative_to(ROOT)),
                    "pdf_render_ms": pdf_ms,
                    "buckets": buckets,
                }
            )
        result["renders"] = renders
        result["memory"] = mem_report(f"{mode} after renders")
    else:
        raise SystemExit(f"unknown worker mode {mode!r}")

    result["timings"] = timings
    print("###JSON###" + json.dumps(result) + "###END###")
    return 0


# --------------------------------------------------------------------------- harness (parent)


def run_worker(mode: str, env_extra: dict[str, str]) -> dict[str, object]:
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update(env_extra)
    log = OUT / f"worker_{mode}.log"
    t0 = time.perf_counter()
    with log.open("w", encoding="utf-8", errors="replace") as handle:
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--worker", mode],
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            timeout=300,
            check=False,
        )
    wall = round((time.perf_counter() - t0) * 1000, 1)
    text = log.read_text(encoding="utf-8", errors="replace")
    payload: dict[str, object] = {}
    if "###JSON###" in text:
        payload = json.loads(text.split("###JSON###", 1)[1].split("###END###", 1)[0])
    payload["exit_code"] = proc.returncode
    payload["wall_ms"] = wall
    payload["env"] = env_extra
    if proc.returncode != 0:
        tail = [ln for ln in text.strip().splitlines() if ln.strip()][-6:]
        payload["log_tail"] = tail
    return payload


def combos() -> list[tuple[str, dict[str, str]]]:
    gpu_off = {
        "QTWEBENGINE_CHROMIUM_FLAGS": "--disable-gpu --no-sandbox",
        "QT_QPA_PLATFORM": "windows",
    }
    offscreen = {
        "QTWEBENGINE_CHROMIUM_FLAGS": "--disable-gpu --no-sandbox",
        "QT_QPA_PLATFORM": "offscreen",
    }
    return [
        ("view-window", gpu_off),
        ("view-offscreen", offscreen),
        ("pdf-window", gpu_off),
        ("view-reuse", gpu_off),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch-assets", action="store_true")
    parser.add_argument("--worker", default=None, help="internal: run one strategy in-process")
    args = parser.parse_args(argv)

    if args.fetch_assets:
        return fetch_assets()
    if args.worker:
        try:
            return worker(args.worker)
        except Exception:
            traceback.print_exc()
            return 3

    missing = [
        str(p)
        for p in (
            ASSETS / "katex" / "katex.min.js",
            ASSETS / "mermaid" / "dist" / "mermaid.min.js",
        )
        if not p.is_file()
    ]
    if missing:
        print("missing assets, run with --fetch-assets first:")
        for path in missing:
            print("  ", path)
        return 4

    print(f"python={sys.version.split()[0]} executable={sys.executable}")
    results = []
    for mode, env in combos():
        print(f"\n=== worker {mode} env={env}")
        try:
            payload = run_worker(mode, env)
        except subprocess.TimeoutExpired:
            payload = {"mode": mode, "exit_code": "timeout", "error": "worker exceeded 300s"}
        ok = payload.get("exit_code") == 0 and payload.get("renders")
        print(
            f"    -> exit={payload.get('exit_code')} wall={payload.get('wall_ms')}ms "
            f"platform={payload.get('platform')} renders={len(payload.get('renders') or [])} ok={ok}"
        )
        if not ok and payload.get("log_tail"):
            for line in payload["log_tail"]:
                print("      |", line)
        results.append(payload)

    summary = {
        "python": sys.version.split()[0],
        "pyside6": __import__("importlib.metadata", fromlist=["version"]).version("PySide6"),
        "katex": KATEX_VERSION,
        "mermaid": MERMAID_VERSION,
        "results": results,
    }
    (OUT / "spike_web_render_result.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nwrote {OUT / 'spike_web_render_result.json'}")
    any_ok = any(r.get("exit_code") == 0 and r.get("renders") for r in results)
    print(
        "VERDICT:",
        "at least one offscreen strategy rendered PNGs" if any_ok else "NOTHING RENDERED",
    )
    return 0 if any_ok else 5


if __name__ == "__main__":
    raise SystemExit(main())
