"""Tests for the offscreen web renderer: real WebEngine, real PNGs, no window.

``QT_QPA_PLATFORM`` is forced here, at module import, because this file lives next to the
source instead of under ``tests/`` (where ``tests/conftest.py`` does it). The platform
plugin must be chosen *before* PySide6 is imported by anything, so the ``setdefault`` below
has to stay above the PySide6 imports.

The assertions deliberately check **pixels**, not just that a file exists. A headless
WebEngine that never composited will happily hand back a flat grey or flat white image, and
an existence-only test passes on that — which is exactly how a broken raster path stayed
green here for a while.

One formula string is shared by three tests: Chromium must start only once for the whole
file, and the second render of the same payload has to be a cache hit.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from mcwr.domain.enums import CardKind  # noqa: E402
from mcwr.infrastructure.web_renderer import QtWebCardRenderer  # noqa: E402

ASSETS_ROOT = Path(__file__).resolve().parents[1] / "assets" / "web"
BUCKET_STEP = 0.5
FORMULA = r"\int_{-\infty}^{\infty} e^{-x^{2}}\,dx=\sqrt{\pi}"
DIAGRAM = "graph TD\n  A[Markdown] --> B{Kind?}\n  B -->|math| C[KaTeX]"


def _dark_pixels(image_path: Path) -> tuple[int, int, int]:
    """Return (dark pixel count, width, height) — the proof that something was drawn."""
    from PySide6.QtGui import QImage

    image = QImage(str(image_path))
    assert not image.isNull(), f"{image_path} is not a readable image"
    rgb = image.convertToFormat(QImage.Format.Format_RGB32)
    width, height, stride = rgb.width(), rgb.height(), rgb.bytesPerLine()
    bits = bytes(rgb.constBits())
    dark = 0
    for y in range(0, height, 2):
        row = bits[y * stride : (y + 1) * stride]
        for offset in range(0, min(len(row), width * 4), 8):
            if row[offset] < 200 or row[offset + 1] < 200 or row[offset + 2] < 200:
                dark += 1
    return dark, width, height


@pytest.fixture(scope="module")
def renderer(tmp_path_factory: pytest.TempPathFactory) -> QtWebCardRenderer:
    """The process-wide renderer (one Chromium start for the whole process).

    Built through :func:`shared_renderer`, not directly: a second hidden view in the same
    process measured an 11x slowdown (17.2 s -> 200.7 s, ERRORS.md E-016), and another test
    module (`tests/integration/test_body_render.py`) renders in this same pytest process.
    """
    from PySide6.QtWidgets import QApplication

    from mcwr.infrastructure.web_renderer import shared_renderer

    QApplication.instance() or QApplication([])
    cache = tmp_path_factory.mktemp("web-cache")
    shared = shared_renderer(ASSETS_ROOT, cache)
    shared.bucket_step = BUCKET_STEP
    shared.timeout_ms = 20000
    return shared


@pytest.fixture(scope="module")
def formula_png(renderer: QtWebCardRenderer) -> Path:
    """The first real render; other tests build on this cached file."""
    path = renderer.render(kind=CardKind.MATH_BLOCK, source=FORMULA, scale=1.0)
    assert path is not None, f"render failed: {renderer.last_error}"
    return path


def _artifacts_dir() -> Path:
    """``spikes/_out/`` — gitignored, where the Lead looks at rendered samples."""
    return Path(__file__).resolve().parents[3] / "spikes" / "_out"


def _save_artifact(source: Path, name: str) -> Path:
    """Copy one render into the gitignored spike output dir for the Lead to eyeball."""
    target = _artifacts_dir() / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    assert target.stat().st_size > 0
    return target


@pytest.mark.slow
def test_a_formula_renders_to_a_png_with_visible_content(
    renderer: QtWebCardRenderer, formula_png: Path
) -> None:
    dark, width, height = _dark_pixels(formula_png)
    assert width > 100 and height > 20, (width, height)
    assert dark > 50, f"only {dark} dark pixels: the formula was not drawn"
    # Deltas, not absolutes: the renderer is a process-wide singleton, so another test
    # module may already have rendered something before this one runs.
    assert renderer.stats["rendered"] >= 1, "the formula must count as a real render"
    assert renderer.last_error is None
    _save_artifact(formula_png, "render_card_math_z1.0.png")


@pytest.mark.slow
def test_a_mermaid_diagram_renders_to_a_png_with_visible_content(
    renderer: QtWebCardRenderer,
) -> None:
    path = renderer.render(kind=CardKind.MERMAID, source=DIAGRAM, scale=1.0)
    assert path is not None, f"render failed: {renderer.last_error}"
    dark, width, height = _dark_pixels(path)
    assert width > 100 and height > 100, (width, height)
    assert dark > 200, f"only {dark} dark pixels: the diagram was not drawn"
    _save_artifact(path, "render_card_mermaid_z1.0.png")


@pytest.mark.slow
def test_a_second_identical_call_hits_the_cache(
    renderer: QtWebCardRenderer, formula_png: Path
) -> None:
    rendered_before = renderer.stats["rendered"]
    hits_before = renderer.stats["cache_hits"]
    again = renderer.render(kind=CardKind.MATH_BLOCK, source=FORMULA, scale=1.0)
    assert again == formula_png
    assert renderer.stats["cache_hits"] == hits_before + 1
    assert renderer.stats["rendered"] == rendered_before  # Chromium was not asked again


@pytest.mark.slow
def test_different_scale_buckets_produce_different_and_larger_files(
    renderer: QtWebCardRenderer, formula_png: Path
) -> None:
    doubled = renderer.render(kind=CardKind.MATH_BLOCK, source=FORMULA, scale=2.0)
    assert doubled is not None, f"render failed: {renderer.last_error}"
    assert doubled != formula_png
    base_dark, base_w, base_h = _dark_pixels(formula_png)
    big_dark, big_w, big_h = _dark_pixels(doubled)
    assert big_w > base_w and big_h > base_h, ((base_w, base_h), (big_w, big_h))
    assert big_dark > base_dark  # the zoomed raster really carries more ink
    _save_artifact(doubled, "render_card_math_z2.0.png")


@pytest.mark.slow
def test_scales_inside_one_bucket_share_a_file(renderer: QtWebCardRenderer) -> None:
    assert renderer.bucket_for(1.0) == 1.0
    assert renderer.bucket_for(1.2) == 1.0
    assert renderer.bucket_for(1.4) == 1.5
    assert renderer.cache_path(kind=CardKind.MATH_BLOCK, source=FORMULA, scale=1.2) == (
        renderer.cache_path(kind=CardKind.MATH_BLOCK, source=FORMULA, scale=1.0)
    )


@pytest.mark.slow
def test_the_returned_path_lies_under_the_cache_dir(
    renderer: QtWebCardRenderer, formula_png: Path
) -> None:
    assert formula_png.parent == renderer.cache_dir
    assert formula_png.is_file()
    assert formula_png.suffix == ".png"


@pytest.mark.slow
def test_the_renderer_reuses_one_hidden_page(renderer: QtWebCardRenderer) -> None:
    """R2: one page for the process, never a page per card, and it is never on screen."""
    from PySide6.QtCore import Qt

    first = renderer._ensure_view()
    assert renderer._ensure_view() is first
    assert renderer._view is first
    assert first.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)


def test_missing_assets_return_none_instead_of_raising(tmp_path: Path) -> None:
    """A package without the web assets degrades to the text fallback, never crashes."""
    empty = tmp_path / "empty-assets"
    (empty / "katex").mkdir(parents=True)
    (empty / "mermaid" / "dist").mkdir(parents=True)
    broken = QtWebCardRenderer(empty, tmp_path / "cache")
    assert broken.render(kind=CardKind.MATH_BLOCK, source=FORMULA, scale=1.0) is None
    assert broken.stats["failed"] >= 1
    assert broken.last_error is not None and "missing web assets" in broken.last_error
    assert broken.failures  # the reason is recorded for the GUI warning
    assert list((tmp_path / "cache").glob("*.png")) == []


def test_assets_are_read_from_the_given_root() -> None:
    """Guards the asset layout itself: KaTeX at katex/, Mermaid at mermaid/dist/."""
    renderer = QtWebCardRenderer(ASSETS_ROOT, Path("unused-cache"))
    assert renderer._missing_assets() == []


def test_a_kind_that_needs_no_web_render_is_a_silent_none(renderer: QtWebCardRenderer) -> None:
    """No Chromium start, no failure record: the card simply stays text."""
    failed_before = renderer.stats["failed"]
    assert renderer.render(kind=CardKind.CODE, source="print(1)", scale=1.0) is None
    assert renderer.stats["failed"] == failed_before
    assert len(renderer.failures) == failed_before


def test_content_cannot_break_out_of_the_cache_directory(renderer: QtWebCardRenderer) -> None:
    """The cache file name is a digest: hostile Markdown cannot steer the write path."""
    hostile = "../../etc/passwd\x00<script>alert(1)</script>"
    path = renderer.cache_path(kind=CardKind.MATH_BLOCK, source=hostile, scale=1.0)
    assert path.parent == renderer.cache_dir
    assert path.name.startswith("web-math-")
    assert "passwd" not in path.name and "script" not in path.name


def test_the_blank_guard_rejects_a_flat_image() -> None:
    """The guard that keeps an empty raster out of the cache (regression: it once passed
    the flat light-grey surface a headless WebEngine returns when it never composited)."""
    from PySide6.QtGui import QImage

    from mcwr.infrastructure.web_renderer import _is_blank

    for colour in ("#ffffff", "#efefef", "#000000"):
        flat = QImage(200, 80, QImage.Format.Format_RGB32)
        flat.fill(colour)
        assert _is_blank(flat), f"{colour} is a flat image and must count as blank"

    assert _is_blank(QImage())  # a null image is blank, not an exception

    drawn = QImage(200, 80, QImage.Format.Format_RGB32)
    drawn.fill("#ffffff")
    for x in range(20, 180):
        drawn.setPixelColor(x, 40, drawn.pixelColor(20, 40).darker(400))
    assert not _is_blank(drawn)


def _scripted_renderer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> QtWebCardRenderer:
    """A renderer whose page layer is faked, so the retry ladder can be driven exactly."""
    renderer = QtWebCardRenderer(ASSETS_ROOT, tmp_path)
    monkeypatch.setattr(renderer, "_missing_assets", list)
    monkeypatch.setattr(renderer, "_ensure_app", object)
    monkeypatch.setattr(renderer, "_ensure_view", lambda: None)
    # The page layer is fake, so the theme switch (which talks to the page) is faked too.
    monkeypatch.setattr(renderer, "_apply_page_theme", lambda _theme: True)
    monkeypatch.setattr(renderer, "_render_in_page", lambda **_: (200, 80))
    return renderer


def _drawn_image() -> object:
    from PySide6.QtGui import QImage

    image = QImage(200, 80, QImage.Format.Format_RGB32)
    image.fill("#ffffff")
    for x in range(0, 40, 2):
        for y in range(0, 40, 2):
            image.setPixelColor(x, y, image.pixelColor(0, 0).darker(400))
    return image


def test_a_blank_raster_is_retried_and_then_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-016: the blank-raster ladder must recover, not lose the card on the first try."""
    renderer = _scripted_renderer(tmp_path, monkeypatch)
    attempts = {"n": 0}

    def fake_rasterize(*, size: tuple[int, int], scale: float) -> object:
        del size, scale
        attempts["n"] += 1
        if attempts["n"] < 3:
            renderer._last_reason = "rasterized image is blank"
            return None
        return _drawn_image()

    monkeypatch.setattr(renderer, "_rasterize", fake_rasterize)

    path = renderer.render(kind=CardKind.MATH_BLOCK, source="x^2 + y^2", scale=1.0)

    assert path is not None, f"the ladder should recover: {renderer.last_error}"
    assert attempts["n"] == 3, "two blank rasters then a good one must be enough"
    assert renderer.stats["retried"] >= 1
    assert renderer.stats["rendered"] == 1


def test_a_permanently_blank_raster_gives_up_after_the_bounded_ladder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-016: no unbounded retry (D-022 item 8) — exactly `_BLANK_ATTEMPTS` tries, then fail."""
    from mcwr.infrastructure.web_renderer import _BLANK_ATTEMPTS

    renderer = _scripted_renderer(tmp_path, monkeypatch)
    attempts = {"n": 0}

    def always_blank(*, size: tuple[int, int], scale: float) -> object:
        del size, scale
        attempts["n"] += 1
        renderer._last_reason = "rasterized image is blank"
        return None

    monkeypatch.setattr(renderer, "_rasterize", always_blank)

    path = renderer.render(kind=CardKind.MERMAID, source="graph TD; A-->B;", scale=1.0)

    assert path is None
    assert attempts["n"] == _BLANK_ATTEMPTS, "the ladder must be bounded, not a retry loop"
    assert f"after {_BLANK_ATTEMPTS} attempt(s)" in (renderer.last_error or "")
    assert renderer.failures, "the reason must be recorded for the log/status message"


# ------------------------------------------------------------------ theme (T-024 ④)


def _mean_luminance(image_path: Path) -> float:
    """Mean perceived brightness of a raster: light cards stay high, dark cards low."""
    from PySide6.QtGui import QImage

    image = QImage(str(image_path))
    assert not image.isNull(), f"{image_path} is not a readable image"
    rgb = image.convertToFormat(QImage.Format.Format_RGB32)
    width, height, stride = rgb.width(), rgb.height(), rgb.bytesPerLine()
    bits = bytes(rgb.constBits())
    total = 0
    sampled = 0
    for y in range(0, height, 2):
        row = bits[y * stride : (y + 1) * stride]
        for offset in range(0, min(len(row), width * 4), 8):
            red, green, blue = row[offset], row[offset + 1], row[offset + 2]
            total += (red * 299 + green * 587 + blue * 114) // 1000
            sampled += 1
    assert sampled > 0
    return total / sampled


def _light_pixels(image_path: Path) -> int:
    """Pixels that are near-white: the proof that ink was drawn on a dark fill."""
    from PySide6.QtGui import QImage

    image = QImage(str(image_path)).convertToFormat(QImage.Format.Format_RGB32)
    width, height, stride = image.width(), image.height(), image.bytesPerLine()
    bits = bytes(image.constBits())
    light = 0
    for y in range(0, height, 2):
        row = bits[y * stride : (y + 1) * stride]
        for offset in range(0, min(len(row), width * 4), 4):
            if row[offset] > 180 and row[offset + 1] > 180 and row[offset + 2] > 180:
                light += 1
    return light


def test_the_cache_key_separates_the_two_themes(renderer: QtWebCardRenderer) -> None:
    """Visual spec §5: the theme is part of the digest, so a dark card is its own file."""
    light = renderer.cache_path(kind=CardKind.MATH_BLOCK, source=FORMULA, scale=1.0)
    dark = renderer.cache_path(kind=CardKind.MATH_BLOCK, source=FORMULA, scale=1.0, theme="dark")
    assert light != dark
    assert light == renderer.cache_path(
        kind=CardKind.MATH_BLOCK, source=FORMULA, scale=1.0, theme="light"
    )
    # An unknown theme must not fork the cache into a third namespace.
    assert (
        renderer.cache_path(kind=CardKind.MATH_BLOCK, source=FORMULA, scale=1.0, theme="neon")
        == light
    )


@pytest.mark.slow
def test_a_dark_math_card_is_printed_on_the_dark_fill(renderer: QtWebCardRenderer) -> None:
    """T-024 ④: dark really means dark — Chromium must print the fill, not white paper."""
    light = renderer.render(kind=CardKind.MATH_BLOCK, source=FORMULA, scale=1.0, theme="light")
    dark = renderer.render(kind=CardKind.MATH_BLOCK, source=FORMULA, scale=1.0, theme="dark")
    assert light is not None, f"light render failed: {renderer.last_error}"
    assert dark is not None, f"dark render failed: {renderer.last_error}"
    assert dark != light, "the two themes must never share one raster"
    assert _mean_luminance(light) > 200.0, "the light theme must stay light"
    assert _mean_luminance(dark) < 96.0, "the dark card was printed on a white fill"
    assert _light_pixels(dark) > 50, "the formula must be drawn in light ink on the dark fill"
    _save_artifact(dark, "render_card_math_dark_z1.0.png")


@pytest.mark.slow
def test_a_dark_mermaid_card_is_printed_on_the_dark_fill(renderer: QtWebCardRenderer) -> None:
    """T-024 ④ for diagrams: the Mermaid dark theme must be applied, not just the CSS."""
    dark = renderer.render(kind=CardKind.MERMAID, source=DIAGRAM, scale=1.0, theme="dark")
    assert dark is not None, f"dark render failed: {renderer.last_error}"
    assert _mean_luminance(dark) < 96.0, "the dark diagram was drawn on a white fill"
    assert _light_pixels(dark) > 50, "the diagram's glyphs and edges must be visible"
    _save_artifact(dark, "render_card_mermaid_dark_z1.0.png")


def test_the_shell_file_is_content_addressed(tmp_path: Path) -> None:
    """E-021: the shell URL must change with its content, or Chromium serves a stale copy.

    A constant ``_shell.html`` URL was answered from the previous version's disk cache after
    an upgrade: the page had ``mcwrRender`` and reported ready, but had no ``mcwrSetTheme``,
    so every dark render raised "not a function" while the light path looked healthy.
    """
    renderer = QtWebCardRenderer(ASSETS_ROOT, tmp_path)
    shell = renderer._write_shell()
    assert shell.is_file()
    assert shell.name.startswith("_shell-") and shell.name.endswith(".html")
    assert shell.name != "_shell.html", "the pre-E-021 name must not be reused"

    text = shell.read_text(encoding="utf-8")
    assert "mcwrSetTheme" in text and "mcwrRender" in text
    assert renderer._write_shell() == shell, "the same content keeps one file"


def test_the_shell_url_changes_when_the_shell_changes() -> None:
    """The digest in the name is what makes a stale cached page unreachable."""
    from mcwr.infrastructure.web_renderer import _shell_file_name

    first = _shell_file_name("<html>one</html>")
    assert first == _shell_file_name("<html>one</html>")
    assert first != _shell_file_name("<html>two</html>")
    assert first.startswith("_shell-") and first.endswith(".html")


# ------------------------------------------------------------ capped cache (T-017)


def _paging_renderer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, cap: int
) -> QtWebCardRenderer:
    """A renderer whose page *and* raster layers are faked, so files appear deterministically."""
    renderer = _scripted_renderer(tmp_path, monkeypatch)
    renderer.max_cache_entries = cap
    monkeypatch.setattr(renderer, "_rasterize", lambda **_: _drawn_image())
    return renderer


def _render(renderer: QtWebCardRenderer, source: str) -> Path:
    path = renderer.render(kind=CardKind.MATH_BLOCK, source=source, scale=1.0)
    assert path is not None, f"render failed: {renderer.last_error}"
    return path


def test_the_default_cache_cap_is_the_value_the_user_gave() -> None:
    from mcwr.infrastructure.web_renderer import MAX_CACHE_ENTRIES

    assert MAX_CACHE_ENTRIES == 1024


def test_the_cache_keeps_at_most_the_cap_and_drops_the_oldest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    renderer = _paging_renderer(tmp_path, monkeypatch, cap=3)
    first = _render(renderer, "payload 0")
    for index in range(1, 4):
        time.sleep(0.01)  # distinct mtimes, so "oldest" is unambiguous
        _render(renderer, f"payload {index}")

    rasters = sorted(path.name for path in tmp_path.glob("web-*.png"))
    assert len(rasters) == 3, rasters
    assert len(list(tmp_path.iterdir())) <= 3
    assert renderer.stats["evicted"] == 1
    assert first.is_file() is False, "the oldest raster is the one that goes"


def test_a_cache_hit_refreshes_recency_so_a_used_raster_survives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    renderer = _paging_renderer(tmp_path, monkeypatch, cap=2)
    alpha = _render(renderer, "alpha")
    time.sleep(0.01)
    beta = _render(renderer, "beta")
    time.sleep(0.01)

    assert renderer.render(kind=CardKind.MATH_BLOCK, source="alpha", scale=1.0) == alpha
    hits_before = renderer.stats["cache_hits"]
    assert hits_before == 1

    time.sleep(0.01)
    gamma = _render(renderer, "gamma")

    assert alpha.is_file(), "the raster read again must outlive the untouched one"
    assert gamma.is_file()
    assert beta.is_file() is False, "beta was the least recently used"


def test_pruning_also_collects_stale_shell_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E-021 left ``_shell-<digest>.html`` copies behind; the cap must collect them too."""
    from mcwr.infrastructure.web_renderer import _SHELL_NAME_PREFIX

    renderer = _paging_renderer(tmp_path, monkeypatch, cap=2)
    stale = tmp_path / f"{_SHELL_NAME_PREFIX}deadbeef.html"
    stale.write_text("<html>old shell</html>", encoding="utf-8")
    legacy = tmp_path / "_shell.html"
    legacy.write_text("<html>pre-E-021 shell</html>", encoding="utf-8")
    os.utime(stale, (1.0, 1.0))
    os.utime(legacy, (2.0, 2.0))

    first = _render(renderer, "a")
    second = _render(renderer, "b")

    assert stale.is_file() is False and legacy.is_file() is False
    assert first.is_file() and second.is_file()


def test_the_active_shell_and_the_working_pdf_are_never_evicted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    renderer = _paging_renderer(tmp_path, monkeypatch, cap=3)
    shell = renderer._write_shell()
    pdf = tmp_path / "_page.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    os.utime(shell, (1.0, 1.0))
    os.utime(pdf, (2.0, 2.0))

    first = _render(renderer, "a")
    time.sleep(0.01)
    second = _render(renderer, "b")

    assert shell.is_file(), "the page is loaded from this file"
    assert pdf.is_file(), "the PDF is written and read inside one render"
    assert sum(1 for path in (first, second) if path.is_file()) == 1, "one raster had to go"


def test_pruning_a_missing_directory_is_not_an_error(tmp_path: Path) -> None:
    renderer = QtWebCardRenderer(ASSETS_ROOT, tmp_path / "never-created")
    renderer._prune_cache()  # must not raise: the render path degrades, never fails
    assert renderer.stats["evicted"] == 0


def test_pruning_at_the_production_cap_keeps_the_directory_within_it(tmp_path: Path) -> None:
    """The arithmetic at the real cap (1024) matters, not only at the tiny test caps."""
    from mcwr.infrastructure.web_renderer import MAX_CACHE_ENTRIES

    renderer = QtWebCardRenderer(ASSETS_ROOT, tmp_path)
    for index in range(MAX_CACHE_ENTRIES + 5):
        (tmp_path / f"web-math-{index:04d}.png").write_bytes(b"x")
    assert len(list(tmp_path.iterdir())) == MAX_CACHE_ENTRIES + 5

    renderer._prune_cache()

    assert len(list(tmp_path.iterdir())) == MAX_CACHE_ENTRIES
    assert renderer.stats["evicted"] == 5
