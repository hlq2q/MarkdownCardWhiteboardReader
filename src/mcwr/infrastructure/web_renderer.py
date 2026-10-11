"""Offscreen KaTeX/Mermaid rasterizer: a live web widget cannot scale with the canvas (D14, R2).

The whiteboard has one canvas transform (D7), so a live ``QWebEngineView`` inside a card
would blur and desync hit-testing when zoomed (R2). WebEngine is therefore used **only as
a rasterizer**: it turns one math/diagram payload into a PNG, and the canvas draws that PNG
as a static pixmap.

Why the raster comes from the page's PDF, not from a widget grab
--------------------------------------------------------------
A hidden ``QWebEngineView`` in a headless process never composites: ``grab()`` returns the
**unpainted widget surface** — flat light grey (or flat white) with no content at all — even
though the page has rendered and reports its content box correctly. That was measured on
``QT_QPA_PLATFORM`` ``offscreen`` and on ``windows`` with ``WA_DontShowOnScreen``, both with
and without ``--disable-gpu``/``--no-sandbox``. So the renderer never grabs: the page is
printed to PDF with Chromium's own layout engine (``QWebEnginePage.printToPdf``), and the
PDF is rasterized at the requested zoom with ``QPdfDocument.render``. That path is fully
offscreen, crisp at every zoom (vector source), and returns a **blank image** instead of a
plausible-looking one when something goes wrong, which the blank guard below then rejects.

Lifecycle (one hidden page per process)
--------------------------------------
``QtWebCardRenderer`` reuses *one* hidden ``QWebEngineView`` for its whole life. Chromium
starts once, on the first successful render; every later request only calls
``runJavaScript`` on the already-loaded shell. Creating a page per card is exactly the cost
R2 warns about (each page spawns work in the render process), so the view is created
lazily, parented to the renderer's own hidden widget, and never torn down: QtWebEngine
supports neither safe repeated initialisation nor teardown inside one process, and the
process is expected to exit with the application. Editing the shell HTML invalidates the
cached ``_shell.html`` copy (the asset paths are embedded in it).

Environment flags (must be set *before* QtWebEngineCore initialises)
-------------------------------------------------------------------
Importing this module sets, with ``setdefault``, the two flags the feasibility spike proved
necessary and sufficient on Windows:

* ``QTWEBENGINE_DISABLE_SANDBOX=1`` — the Chromium sandbox cannot start here;
* ``QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu --no-sandbox
  --disable-features=AudioServiceOutOfProcess`` — no GPU process is available, and the
  audio service is both useless and a hang risk.

One flag **cannot** be set here: ``QT_QPA_PLATFORM``. The platform plugin is chosen by the
process that imports Qt, so a headless caller (a test module, a batch export) must set
``QT_QPA_PLATFORM=offscreen`` before importing PySide6 at all — by the time this module is
imported a ``QApplication`` may already exist and the choice is fixed. The PDF path above
works on both ``offscreen`` and a normal desktop session, and no window is ever shown.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Final

os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--disable-gpu --no-sandbox --disable-features=AudioServiceOutOfProcess",
)

from collections.abc import Callable  # noqa: E402
from functools import partial  # noqa: E402
from typing import cast  # noqa: E402

from PySide6.QtCore import QEventLoop, QMarginsF, QSize, QSizeF, Qt, QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QImage, QPageLayout, QPageSize  # noqa: E402
from PySide6.QtPdf import QPdfDocument  # noqa: E402
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings  # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from mcwr.domain.enums import CardKind  # noqa: E402

_CACHE_PREFIX: Final[str] = "web-"
_KIND_TAGS: Final[dict[CardKind, str]] = {
    CardKind.MATH_BLOCK: "math",
    CardKind.MERMAID: "mermaid",
}
_THEME_LIGHT: Final[str] = "light"
_THEME_DARK: Final[str] = "dark"
"""The two raster themes: the cache digest and the page both key off exactly these words."""
_STAGE_WIDTH: Final[int] = 480
"""CSS width of the render stage: a representative card-body width on the whiteboard."""
_SHELL_NAME: Final[str] = "_shell.html"
_PDF_NAME: Final[str] = "_page.pdf"
_MIN_SCALE: Final[float] = 0.25
_MIN_BUCKET_STEP: Final[float] = 0.01
_MAX_SCALE_BUCKET: Final[float] = 4.0
_DIGEST_CHARS: Final[int] = 32
_POLL_SLICE_MS: Final[int] = 1500
"""How long one JS evaluation is given before the poll re-asks (see ``_wait_for``).

This must exceed the round trip of a single ``runJavaScript`` answer, which was measured at
~300 ms in the running application (a busy main thread slows the render process's reply).
At the previous 250 ms every slice expired just before its own answer arrived, so the poll
restarted the command instead of reading its result: a 15 s budget bought only ~11 reads,
fewer than a Mermaid render needs, and every card timed out while the page itself reported
successful renders."""
_VIEW_WIDTH: Final[int] = 1280
_VIEW_HEIGHT: Final[int] = 1024
"""Viewport of the one hidden view. Large enough that the stage never reflows."""
_MAX_RASTER_EDGE: Final[int] = 8000
"""Ceiling for a raster edge; a request above it is stepped down to the nearest bucket."""
_UNIFORM_RANGE: Final[int] = 24
"""Per-channel spread below which an image counts as one flat colour, i.e. blank."""
_BLANK_SCAN_STEP: Final[int] = 4
"""Rows and pixels skipped while looking for contrast in a raster (see ``_is_blank``)."""
_RETRY_PAUSE_MS: Final[int] = 250
"""Pause before re-printing after a blank raster (grows with each attempt)."""
_BLANK_ATTEMPTS: Final[int] = 3
"""Bounded attempts against a blank raster; no unbounded retry loop (D-022 item 8)."""
DEFAULT_TIMEOUT_MS: Final[int] = 15000
"""Default per-step budget for starting Chromium, loading a page or rendering a payload.

The feasibility spike used 5000 ms, which holds once the process is warm but not on the
first card of a cold run: starting Chromium, then parsing the 5.3 MB Mermaid bundle and
laying out its SVG routinely exceeds 5 s on a first render with an empty cache. Renderers
are created lazily by the container, so that cost lands on the first math/Mermaid card."""

_SHELL_HTML: Final[str] = """<!doctype html>
<html><head><meta charset="utf-8">
<link rel="stylesheet" href="{katex_css}">
<style>
  html, body {{ margin:0; padding:0; background:{light_bg}; color:{light_fg};
               -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
  #stage {{ display:block; width:{stage_width}px; padding:8px; background:{light_bg};
            color:{light_fg}; box-sizing:content-box;
            -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
  .katex-display {{ margin:0.4em 0; }}
  .katex {{ font-size:20px; color:inherit; }}
  /* A diagram scales down to the card width but is never stretched beyond its own size:
     forcing width:100% turned a small flowchart into a tall narrow column. */
  #stage svg {{ max-width:100%; height:auto; }}
</style>
</head><body><div id="stage"></div>
<script src="{katex_js}"></script>
<script src="{mermaid_js}"></script>
<script>
window.mcwrState = "boot";
window.mcwrError = null;
window.mcwrRenders = 0;
window.mcwrSizeJson = "";
window.mcwrTheme = "light";
let seq = 0;

/* Theme switch (T-024, visual spec §5). The page carries BOTH themes, so switching is a
   JS call and never a page reload: a reload would race with the render submitted right
   after it. Chromium prints element backgrounds only with print-color-adjust:exact, which
   is why the stage fill is set inline as well as in the style block above. */
window.mcwrSetTheme = function (theme) {{
  const dark = String(theme) === "dark";
  const bg = dark ? "{dark_bg}" : "{light_bg}";
  const fg = dark ? "{dark_fg}" : "{light_fg}";
  document.documentElement.style.background = bg;
  document.documentElement.style.color = fg;
  document.body.style.background = bg;
  document.body.style.color = fg;
  const stage = document.getElementById("stage");
  stage.style.background = bg;
  stage.style.color = fg;
  mermaid.initialize({{startOnLoad: false, theme: dark ? "dark" : "neutral",
                      securityLevel: "loose", fontFamily: "{ui_font}"}});
  window.mcwrTheme = dark ? "dark" : "light";
  return true;
}};

/* The payload's content box and the end of its render are reported together: two separate
   runJavaScript commands are queued independently, so a size readback issued as its own
   command can answer with the PREVIOUS payload's box (that produced clipped rasters). */
function report() {{
  const stage = document.getElementById("stage");
  const box = stage.getBoundingClientRect();
  window.mcwrSizeJson = JSON.stringify([
    Math.ceil(box.width), Math.ceil(box.height), 0,
  ]);
  return window.mcwrSizeJson;
}}

function done() {{
  window.mcwrState = "done";
  window.mcwrRenders += 1;
  return report();
}}

function failed(message) {{
  window.mcwrError = String(message);
  window.mcwrState = "error";
  window.mcwrRenders += 1;
  return null;
}}

window.mcwrRender = function (kind, payload) {{
  /* The counter rises when a render STARTS, so the Python side can tell "this payload has
     been picked up" from "the previous payload is still the finished one". Without that, a
     wait for "counter == n" is either satisfied by a stale value or never satisfied. */
  window.mcwrRenders += 1;
  window.mcwrState = "busy";
  window.mcwrError = null;
  const stage = document.getElementById("stage");
  try {{
    if (kind === "math") {{
      stage.innerHTML = "";
      const box = document.createElement("div");
      katex.render(payload, box, {{displayMode: true, throwOnError: false}});
      stage.appendChild(box);
      return Promise.resolve(done());
    }}
    if (kind === "mermaid") {{
      return mermaid.render("mmd" + (++seq), payload).then(function (res) {{
        stage.innerHTML = res.svg;
        return done();
      }}).catch(function (e) {{
        return failed(e);
      }});
    }}
    throw new Error("unknown kind " + kind);
  }} catch (e) {{
    return failed(e && e.stack || e);
  }}
}};

mermaid.initialize({{startOnLoad: false, theme: "neutral", securityLevel: "loose"}});
window.mcwrSetTheme("light");
window.mcwrState = "ready";
</script>
</body></html>
"""


_VIEWS_CREATED = 0
"""How many hidden web views this process has created.

One per process is the design (decision D-022 item 8, resource management): a second view
in the same process measured a **11x** slowdown (17.2 s -> 200.7 s for the same two-card
render, see ERRORS.md E-016), because QtWebEngine cannot initialise twice cleanly. Tests
assert on this counter so the invariant cannot regress silently.
"""

_SHARED: dict[str, QtWebCardRenderer] = {}


def views_created() -> int:
    """Number of hidden web views created in this process (0 before any render)."""
    return _VIEWS_CREATED


def shared_renderer(assets_root: Path, cache_dir: Path) -> QtWebCardRenderer:
    """Return the process-wide renderer, creating it on first use.

    Production has one window per process, so a singleton is the honest shape; it also
    makes it impossible for a caller to spawn a second Chromium by accident.
    """
    key = "renderer"
    existing = _SHARED.get(key)
    if existing is None:
        existing = QtWebCardRenderer(assets_root, cache_dir)
        _SHARED[key] = existing
    return existing


class QtWebCardRenderer:
    """Renders a math/Mermaid card to a cached PNG through one reused offscreen web page.

    Cache: ``cache_dir / web-<digest>.png``, where the digest is a SHA-256 over
    ``(kind, source, bucketed scale)``. The scale is quantized to ``bucket_step`` (default
    0.5, so 1.0 / 1.5 / 2.0), which bounds the number of rasters per card.

    Failures never propagate: :meth:`render` returns ``None`` and appends a reason to
    :attr:`failures` (also :attr:`last_error`), so the view can keep its text fallback and
    still tell the user that math/Mermaid could not be drawn.
    """

    def __init__(
        self,
        assets_root: Path,
        cache_dir: Path,
        *,
        bucket_step: float = 0.5,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
    ) -> None:
        self.assets_root = Path(assets_root)
        self.cache_dir = Path(cache_dir)
        self.bucket_step = max(float(bucket_step), _MIN_BUCKET_STEP)
        self.timeout_ms = max(int(timeout_ms), 1)
        self.failures: list[str] = []
        """Every failure reason in order; the GUI reads the last one for its warning."""
        self.last_error: str | None = None
        self.stats: dict[str, int] = {"rendered": 0, "cache_hits": 0, "failed": 0, "retried": 0}
        """Observable cache/render counters: ``rendered`` never counts a cache hit."""
        self._app: QApplication | None = None
        self._holder: QWidget | None = None
        self._view: QWebEngineView | None = None
        self._shell_path: Path | None = None
        self._page_theme: str | None = None
        """Which theme the loaded page currently carries; ``None`` means "not applied yet"."""
        self._sequence = 0
        """Render counter, mirrored into the page: tells *this* render from the last one."""
        self._last_reason = "unknown"

    # ------------------------------------------------------------------ public API

    def render(
        self, *, kind: CardKind, source: str, scale: float, theme: str = _THEME_LIGHT
    ) -> Path | None:
        """Return the cached PNG of ``source`` at ``scale`` in ``theme``, or ``None``."""
        try:
            return self._render(kind=kind, source=source, scale=scale, theme=theme)
        except Exception as exc:  # noqa: BLE001 - the port promises never to raise
            return self._fail(f"{kind} render raised {exc!r}")

    def bucket_for(self, scale: float) -> float:
        """Quantize a canvas zoom to the nearest render bucket."""
        raw = min(max(float(scale), _MIN_SCALE), _MAX_SCALE_BUCKET)
        bucket = round(raw / self.bucket_step) * self.bucket_step
        return min(max(round(bucket, 4), _MIN_SCALE), _MAX_SCALE_BUCKET)

    def cache_path(
        self, *, kind: CardKind, source: str, scale: float, theme: str = _THEME_LIGHT
    ) -> Path:
        """Deterministic PNG path for this content, this zoom and this theme (the cache key).

        The theme is part of the digest on purpose (visual spec §5): sharing one file
        between the light and the dark raster would paint a white formula on a dark card.
        """
        tag = _KIND_TAGS.get(kind, kind.value)
        material = (
            f"{kind.value}\x00{source}\x00{self.bucket_for(scale):.4f}"
            f"\x00{_normalize_theme(theme)}"
        )
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:_DIGEST_CHARS]
        return self.cache_dir / f"{_CACHE_PREFIX}{tag}-{digest}.png"

    # ----------------------------------------------------------------- render path

    def _render(
        self, *, kind: CardKind, source: str, scale: float, theme: str = _THEME_LIGHT
    ) -> Path | None:
        if kind not in _KIND_TAGS:
            return None  # not our content: no error, no image, the view keeps its text
        body = source.strip()
        if not body:
            return None
        bucket = self.bucket_for(scale)
        wanted = _normalize_theme(theme)
        path = self.cache_path(kind=kind, source=body, scale=bucket, theme=wanted)
        cached = self._load_cached(path)
        if cached is not None:
            self.stats["cache_hits"] += 1
            return cached
        missing = self._missing_assets()
        if missing:
            return self._fail(f"missing web assets: {', '.join(missing)}")
        app = self._ensure_app()
        if app is None:
            return self._fail("QtWebEngine needs a QApplication: create one before rendering")
        try:
            self._ensure_view()
        except RuntimeError as exc:
            return self._fail(f"web page could not be prepared: {exc}")
        theme_problem = self._ensure_page_theme(wanted)
        if theme_problem is not None:
            return self._fail(theme_problem)
        size = self._render_in_page(kind=kind, body=body)
        if isinstance(size, str):
            # One self-heal: a page that lost its script (a wedged or half-initialised
            # render process) reports a timeout, and a fresh load of the shell recovers it.
            self._reload_shell()
            size = self._render_in_page(kind=kind, body=body)
            if isinstance(size, str):
                return self._fail(f"render failed: {size}")
        image = self._rasterize(size=size, scale=self._scale_that_fits(size, bucket))
        attempts = 1
        while image is None and "blank" in self._last_reason and attempts < _BLANK_ATTEMPTS:
            # A blank raster is the rasterizer's dominant transient (ERRORS.md E-013/E-017):
            # the page is fine, Chromium just printed before the payload was laid out. Retry
            # with a growing pause, and from the second retry on re-issue the payload so the
            # page performs a *fresh* layout pass instead of reprinting a stale one.
            attempts += 1
            self._pump(_RETRY_PAUSE_MS * attempts)
            if attempts > 2:
                self._last_reason = f"blank raster (attempt {attempts - 1}); re-rendering"
                rendered = self._render_in_page(kind=kind, body=body)
                if not isinstance(rendered, str):
                    size = rendered
                else:  # pragma: no cover - the page answered the first time, so this is rare
                    return self._fail(f"render failed while retrying: {rendered}")
            image = self._rasterize(size=size, scale=self._scale_that_fits(size, bucket))
            self.stats["retried"] += 1
        if image is None:
            return self._fail(
                f"render failed after {attempts} attempt(s): {self._last_reason}"
            )
        return self._store(image, path)

    def _scale_that_fits(self, size: tuple[int, int], bucket: float) -> float:
        """Largest scale at or below ``bucket`` whose raster stays under the edge ceiling."""
        width, height = size
        scale = bucket
        while scale > self.bucket_step and (
            width * scale > _MAX_RASTER_EDGE or height * scale > _MAX_RASTER_EDGE
        ):
            scale = round(scale - self.bucket_step, 4)
        return max(scale, self.bucket_step)

    def _rasterize(self, *, size: tuple[int, int], scale: float) -> QImage | None:
        """Print the current page to PDF and rasterize it at ``scale``."""
        pdf = self._print_to_pdf(size)
        if pdf is None:
            return None
        width, height = size
        document = QPdfDocument()
        try:
            status = document.load(str(pdf))
            if status != QPdfDocument.Error.None_ or document.pageCount() < 1:
                self._last_reason = f"rendered PDF could not be read ({status})"
                return None
            image = document.render(0, QSize(int(round(width * scale)), int(round(height * scale))))
        finally:
            document.close()
        if image.isNull():
            self._last_reason = "PDF rasterized to an empty image"
            return None
        if _is_blank(image):
            self._last_reason = "rasterized image is blank"
            return None
        return image

    def _print_to_pdf(self, size: tuple[int, int]) -> Path | None:
        """Ask Chromium to print the current page, sized to exactly the content box.

        The page size is the content box in points (CSS px * 0.75) with no margins, so page
        1 of the PDF *is* the card's image at 1.0 scale; larger buckets are produced by
        rasterizing the same vector page, which is why zooming stays crisp.
        """
        page = self._view_page()
        if page is None:  # pragma: no cover - the view is created before any print
            self._last_reason = "no web page available"
            return None
        width, height = size
        layout = QPageLayout(
            QPageSize(
                QSizeF(max(width, 1) * 0.75, max(height, 1) * 0.75),
                QPageSize.Unit.Point,
                "card",
            ),
            QPageLayout.Orientation.Portrait,
            QMarginsF(0.0, 0.0, 0.0, 0.0),
        )
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        target = self.cache_dir / _PDF_NAME
        finished = {"ok": False}

        def on_finished(path: str, ok: bool) -> None:
            del path
            finished["ok"] = ok

        page.pdfPrintingFinished.connect(on_finished)
        try:
            page.printToPdf(str(target), layout)
            if not self._pump_until(lambda: finished["ok"], self.timeout_ms):
                self._last_reason = f"PDF printing timed out after {self.timeout_ms} ms"
                return None
        finally:
            page.pdfPrintingFinished.disconnect(on_finished)
        if not finished["ok"] or not target.is_file() or target.stat().st_size == 0:
            self._last_reason = "Chromium produced no PDF"
            return None
        return target

    # ---------------------------------------------------------------- page control

    def _ensure_page_theme(self, theme: str) -> str | None:
        """Put the page into ``theme`` once; returns a failure reason, or ``None``.

        The page carries both themes, so switching is a JS call rather than a reload —
        a reload between deciding to render and submitting the payload would race with it.
        A page that will not switch (a wedged render process) is reloaded once; if it still
        refuses, the render fails instead of caching a light raster under the dark key.
        """
        if self._page_theme == theme:
            return None
        if not self._apply_page_theme(theme):
            self._reload_shell()
            if not self._apply_page_theme(theme):
                return f"the render page would not switch to the {theme} theme"
        self._page_theme = theme
        return None

    def _apply_page_theme(self, theme: str) -> bool:
        """Call the shell's ``mcwrSetTheme``; ``True`` only on its own ``true`` answer."""
        page = self._view_page()
        if page is None:  # pragma: no cover - the view exists before any theme switch
            return False
        box: dict[str, object] = {"value": None}
        done = {"ok": False}

        def callback(
            value: object,
            _box: dict[str, object] = box,
            _done: dict[str, bool] = done,
        ) -> None:
            _box["value"] = value
            _done["ok"] = True

        page.runJavaScript(f"window.mcwrSetTheme({json.dumps(theme)})", callback)
        if not self._pump_until(partial(_is_ready, done), _POLL_SLICE_MS):
            return False
        return box["value"] is True

    def _render_in_page(self, *, kind: CardKind, body: str) -> tuple[int, int] | str:
        """Run one payload in the page and return its content box, or a failure reason.

        Two ordering traps are handled here, both of which produced wrong images before:

        * ``runJavaScript`` commands are queued, so the *first* poll can run before the
          render command does. The poll therefore waits for the page to acknowledge the
          render counter and to leave the ``busy`` state, which also makes a stale ``done``
          from the previous card unreachable.
        * a size readback issued as its own command can answer with the previous card's
          box, so the box is read from the same atomic expression that detects the end of
          the render.
        """
        page = self._view_page()
        if page is None:  # pragma: no cover - _ensure_view ran before this
            return "no web page available"
        # Every wait is expressed in terms of the PAGE's own counter, read from the page and
        # never tracked locally: the page raises it when a render starts, so "counter has
        # moved past what I saw" means this payload was picked up and has settled. A local
        # counter drifts, and waiting for a number the page can never reach is exactly how
        # every render in the application path timed out while the page reported success.
        before = self._page_renders()
        _trace(f"render_in_page kind={kind.value} page_renders_before={before}")
        page.runJavaScript(f"window.mcwrRender({json.dumps(_KIND_TAGS[kind])}, {json.dumps(body)})")
        answer = self._wait_for(self._result_expression(before), self.timeout_ms)
        if answer is None:
            _trace(
                f"render_in_page TIMEOUT before={before} "
                f"page_renders={self._page_renders()!r} "
                f"state={self._wait_for('String(window.mcwrState)', 2000)!r}"
            )
            return f"timed out after {self.timeout_ms} ms"
        _trace(f"render_in_page ok answer={str(answer)[:60]!r}")
        return self._read_answer(answer)

    def _page_renders(self) -> int | None:
        """Read the page's own render counter, or ``None`` when it cannot be read."""
        page = self._view_page()
        if page is None:  # pragma: no cover - the view exists before any render
            return None
        box: dict[str, object] = {}
        done = {"ok": False}

        def callback(value: object) -> None:
            box["value"] = value
            done["ok"] = True

        page.runJavaScript("window.mcwrRenders | 0", callback)
        if not self._pump_until(lambda: done["ok"], _POLL_SLICE_MS):
            return None
        try:
            return int(str(box["value"]))
        except (TypeError, ValueError):  # pragma: no cover - JS returns a number
            return None

    @staticmethod
    def _result_expression(seen: int | None) -> str:
        """Poll expression: falsy until *this* render has started and settled.

        ``seen`` is the counter observed before the payload was submitted (``None`` when the
        page could not be read, which only means the counter must simply have moved).
        """
        moved = "true" if seen is None else f"window.mcwrRenders > {seen}"
        started = f"({moved})"
        settled = f"({moved} && window.mcwrState !== 'busy')"
        return (
            f"({started} ? (({settled}) ? "
            "(window.mcwrState === 'error' ? "
            "(window.mcwrError ? ('error:' + window.mcwrError) "
            ": 'error: the page reported a failure without a message') : "
            "(window.mcwrSizeJson !== '' ? window.mcwrSizeJson : 'error: no content box')) "
            ": false) : false)"
        )

    def _read_answer(self, answer: object) -> tuple[int, int] | str:
        """Decode the page's answer: ``[width, height, clamped]`` JSON, or an error string."""
        text = str(answer)
        if text.startswith("error:"):
            return text[:200]
        try:
            width, height, clamped = json.loads(text)
        except (TypeError, ValueError):
            return f"unreadable content box: {text[:80]}"
        if clamped:
            return "content is taller than the render stage; it was clamped to fit"
        if int(width) <= 0 or int(height) <= 0:
            return f"content box is empty: {text[:80]}"
        return int(width), int(height)

    # ------------------------------------------------------------------ Qt plumbing

    def _ensure_app(self) -> QApplication | None:
        """The single QApplication of this process (Qt allows exactly one)."""
        if self._app is not None and not _is_deleted(self._app):
            return self._app
        existing = QApplication.instance()
        if existing is None:
            return None
        # ``instance()`` is typed as QCoreApplication; this process only ever creates a
        # QApplication, which is what QtWebEngine requires.
        self._app = cast(QApplication, existing)
        return self._app

    def _ensure_view(self) -> QWebEngineView:
        """Create the one hidden view and load the shell into it (Chromium starts here).

        The view is held on ``self`` together with its holder widget: a Qt object that
        loses its last Python reference is destroyed immediately, and QtWebEngine cannot be
        initialised twice in one process. Nothing is ever grabbed from this widget — it only
        has to host the page (see the module docstring).
        """
        if self._view is not None and not _is_deleted(self._view):
            return self._view
        shell = self._write_shell()
        app = self._ensure_app()
        holder = QWidget(None)  # a hidden top-level keeps the render process owned
        holder.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        view = QWebEngineView(holder)
        view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        settings = view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PrintElementBackgrounds, True)
        view.resize(_VIEW_WIDTH, _VIEW_HEIGHT)
        view.show()
        global _VIEWS_CREATED
        _VIEWS_CREATED += 1
        self._holder = holder
        self._view = view
        loaded = {"ok": False}

        def on_load(ok: bool) -> None:
            loaded["ok"] = ok

        view.page().loadFinished.connect(on_load)
        view.page().load(QUrl.fromLocalFile(str(shell)))
        if app is None or not self._pump_until(lambda: loaded["ok"], self.timeout_ms):
            raise RuntimeError(f"shell page never finished loading ({shell})")
        if not self._wait_until_ready():
            # The page loaded but its script never ran. Reloading once recovers from the
            # transient case (a load that settled before the parser reached the script);
            # without this the failure only surfaced much later as a confusing
            # "window.mcwrRender is not a function" on the first render.
            self._shell_path = None
            loaded["ok"] = False
            view.page().load(QUrl.fromLocalFile(str(self._write_shell())))
            if not self._pump_until(lambda: loaded["ok"], self.timeout_ms) or (
                not self._wait_until_ready()
            ):
                raise RuntimeError(f"shell script never became ready ({shell})")
        self._page_theme = _THEME_LIGHT  # the shell boots light and says so to the page
        return view

    def _reload_shell(self) -> None:
        """Reload the shell page in place, keeping the same view and render process."""
        page = self._view_page()
        if page is None:  # pragma: no cover - only called with a live view
            return
        shell = self._write_shell()
        loaded = {"ok": False}

        def on_load(ok: bool) -> None:
            loaded["ok"] = ok

        page.loadFinished.connect(on_load)
        try:
            page.load(QUrl.fromLocalFile(str(shell)))
            self._pump_until(lambda: loaded["ok"], self.timeout_ms)
        finally:
            page.loadFinished.disconnect(on_load)
        self._wait_until_ready()
        self._page_theme = _THEME_LIGHT  # a reloaded shell is light again

    def _wait_until_ready(self) -> bool:
        """Whether the shell script has finished booting *and* published its entry point.

        Both halves matter: ``mcwrState`` alone is only a string, so checking it by itself
        reports ready for a page whose function was never defined.
        """
        ready = self._wait_for(
            "(typeof window.mcwrRender === 'function' && window.mcwrState === 'ready') "
            "? 'ready' : "
            "(window.mcwrState === 'error' ? ('error:' + window.mcwrError) : false)",
            self.timeout_ms,
        )
        return ready == "ready"

    def _wait_for(self, expression: str, timeout_ms: int) -> object | None:
        """Poll ``expression`` via ``runJavaScript`` until it is truthy or time runs out.

        The expression is re-evaluated rather than evaluated once: a page that is still
        rendering answers ``false`` (or ``undefined``), and a single read would hand that
        "not yet" back as the final answer.
        """
        page = self._view_page()
        if page is None:  # pragma: no cover - the view is created before any wait
            return None
        deadline = time.monotonic() + timeout_ms / 1000.0
        while time.monotonic() < deadline:
            box: dict[str, object] = {"value": None}
            done = {"ok": False}

            def callback(
                value: object,
                _box: dict[str, object] = box,
                _done: dict[str, bool] = done,
            ) -> None:
                _box["value"] = value
                _done["ok"] = True

            page.runJavaScript(expression, callback)
            # A slice that expires without an answer is not a failure: the page may be busy
            # with the render itself, so keep polling until the real deadline.
            self._pump_until(partial(_is_ready, done), _POLL_SLICE_MS)
            value = box["value"]
            if value:  # JS false / null / undefined / 0 all mean "not ready yet"
                return value
        return None

    def _view_page(self) -> QWebEnginePage | None:
        view = self._view
        return None if view is None else view.page()

    def _pump_until(self, predicate: Callable[[], bool], timeout_ms: int) -> bool:
        """Spin a local event loop until ``predicate()`` is true (never nests a second one)."""
        deadline = time.monotonic() + timeout_ms / 1000.0
        while time.monotonic() < deadline:
            if predicate():
                return True
            self._pump(20)
        return predicate()

    @staticmethod
    def _pump(ms: int) -> None:
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    # -------------------------------------------------------------- cache and shell

    def _missing_assets(self) -> list[str]:
        gone: list[str] = []
        for label, path in self._asset_paths().items():
            if not path.is_file():
                gone.append(f"{label} ({path})")
        return gone

    def _load_cached(self, path: Path) -> Path | None:
        """A cached PNG is trusted only while it exists and is not an empty file."""
        try:
            if path.is_file() and path.stat().st_size > 0:
                return path
        except OSError:
            return None
        return None

    def _store(self, image: QImage, path: Path) -> Path | None:
        """Write the raster to the cache and verify it round-trips as a non-blank image."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            # PySide6 takes the format as ``str`` at runtime; its stubs claim ``bytes``.
            if not image.save(str(path), "PNG"):  # type: ignore[call-overload]
                return self._fail(f"could not write {path}")  # pragma: no cover - disk full
            written = QImage(str(path))
            if written.isNull() or _is_blank(written):
                path.unlink(missing_ok=True)
                return self._fail(f"refusing blank PNG for {path.name}")
        except OSError as exc:
            return self._fail(f"cache write failed: {exc}")
        self.stats["rendered"] += 1
        return path

    def _fail(self, reason: str) -> Path | None:
        self.last_error = reason
        self.stats["failed"] += 1
        self.failures.append(reason)
        return None

    def _asset_paths(self) -> dict[str, Path]:
        """Local KaTeX/Mermaid files. No CDN, no network: only what ships in the package."""
        katex = self.assets_root / "katex"
        mermaid = self.assets_root / "mermaid"
        return {
            "katex.min.css": katex / "katex.min.css",
            "katex.min.js": katex / "katex.min.js",
            "mermaid.min.js": mermaid / "dist" / "mermaid.min.js",
        }

    def _write_shell(self) -> Path:
        """Materialize the HTML shell (once per cache dir) with absolute local asset URIs."""
        if self._shell_path is not None and self._shell_path.is_file():
            return self._shell_path
        # The shell's two stage colours *are* the visual spec's ``card_bg``/``text_primary``
        # of each theme, so they are read from the palette instead of being copied here. The
        # import is deliberately local: the palette lives in the GUI layer
        # (``docs/visual-spec.md`` §7) and infrastructure must not import interfaces.
        from mcwr.interfaces.gui.theme import DARK, LIGHT, UI_FONT

        assets = self._asset_paths()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        html = _SHELL_HTML.format(
            katex_css=assets["katex.min.css"].as_uri(),
            katex_js=assets["katex.min.js"].as_uri(),
            mermaid_js=assets["mermaid.min.js"].as_uri(),
            stage_width=_STAGE_WIDTH,
            light_bg=LIGHT.card_bg,
            light_fg=LIGHT.text_primary,
            dark_bg=DARK.card_bg,
            dark_fg=DARK.text_primary,
            ui_font=UI_FONT,
        )
        shell = self.cache_dir / _SHELL_NAME
        shell.write_text(html, encoding="utf-8")
        self._shell_path = shell
        return shell


def _normalize_theme(theme: str) -> str:
    """Map any caller value onto exactly one of the two raster themes.

    Unknown values fall back to light instead of creating a third cache namespace: the
    digest must have a closed set of themes, or a typo would silently fork the cache.
    """
    return _THEME_DARK if str(theme).strip().lower() == _THEME_DARK else _THEME_LIGHT


def _is_blank(image: QImage) -> bool:
    """True when ``image`` carries no *drawn* content: one flat colour, or (nearly) white.

    A rendered payload always paints glyphs and edges, so an empty raster is recognisable:
    every sampled pixel sits inside a single narrow colour band. This is the last line of
    defence for the "never cache a plausible-looking empty image" rule — a headless
    WebEngine that never composited returns a flat grey widget surface, which a naive
    "is it white?" test happily accepts.
    """
    if image.isNull():
        return True
    rgb = image.convertToFormat(QImage.Format.Format_RGB32)
    width, height = rgb.width(), rgb.height()
    if width <= 0 or height <= 0:  # pragma: no cover - isNull already covers this
        return True
    stride = rgb.bytesPerLine()
    bits = bytes(rgb.constBits())
    if len(bits) < stride * height:
        return False  # cannot inspect it: do not throw away a real render
    low = [255, 255, 255]
    high = [0, 0, 0]
    for y in range(0, height, _BLANK_SCAN_STEP):
        row = bits[y * stride : (y + 1) * stride]
        for offset in range(0, min(len(row), width * 4), 4 * _BLANK_SCAN_STEP):
            for channel in range(3):
                value = row[offset + channel]
                if value < low[channel]:
                    low[channel] = value
                if value > high[channel]:
                    high[channel] = value
        # Compare like with like: the spread of ONE channel across the sampled pixels.
        if max(high[c] - low[c] for c in range(3)) > _UNIFORM_RANGE:
            return False  # contrast found, so something was drawn
    return max(high[c] - low[c] for c in range(3)) <= _UNIFORM_RANGE


def _trace(message: str) -> None:
    """Print one diagnostic line when ``MCWR_WEB_RENDER_TRACE`` is set.

    Rendering is a multi-step conversation with another process (page load, payload,
    print, raster), so when it stalls the only useful question is *which* step stalled.
    This is opt-in: the default path stays silent.
    """
    if os.environ.get("MCWR_WEB_RENDER_TRACE"):
        print(f"[webrender {time.monotonic():.3f}] {message}", flush=True)


def _is_ready(flag: dict[str, bool]) -> bool:
    """Predicate for the JS polling loop: has the page answered the current command yet?"""
    return flag["ok"]


def _is_deleted(widget: object) -> bool:
    """Whether a C++ side of a Qt object is already gone (ShutdownError otherwise)."""
    try:
        from shiboken6 import isValid

        return not bool(isValid(widget))
    except Exception:  # noqa: BLE001 - shiboken missing or an unbound object
        return True


__all__ = ["QtWebCardRenderer"]
