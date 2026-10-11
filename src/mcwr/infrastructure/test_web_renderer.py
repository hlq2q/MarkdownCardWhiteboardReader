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
    """One renderer (and therefore one Chromium start) for the whole module."""
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    cache = tmp_path_factory.mktemp("web-cache")
    return QtWebCardRenderer(ASSETS_ROOT, cache, bucket_step=BUCKET_STEP, timeout_ms=20000)


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
    assert renderer.stats["rendered"] == 1
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
    assert broken.stats["failed"] == 1
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
