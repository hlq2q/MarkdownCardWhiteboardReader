"""Spike for T-029: does Pygments HTML survive QTextDocument, and how readable is it?

Two questions are answered *before* card_item is touched:

1. Does ``HtmlFormatter(noclasses=True)`` keep token colours when the fragment is rendered
   through ``QTextDocument.setHtml`` (Qt supports only a subset of CSS)?
2. What is the real WCAG contrast of keyword / comment / string tokens against the visual
   spec's ``code_bg`` for the candidate styles — light ``default``, dark ``monokai``?

Run:  python -m uv run python spikes/spike_pygments_qt.py
Prints one block per style plus a verdict; writes a PNG per style into spikes/_out/ so the
colours can be eyeballed.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pygments import highlight  # noqa: E402
from pygments.formatters import HtmlFormatter  # noqa: E402
from pygments.lexers import PythonLexer  # noqa: E402
from pygments.styles import get_style_by_name  # noqa: E402
from pygments.token import Comment, Keyword, String  # noqa: E402

CODE = '''def slug(text: str) -> str:
    """Lower-case a title and keep CJK."""
    # punctuation goes away
    return "-".join(text.casefold().split())
'''

CANDIDATES = (("light", "default", "#F1F4F7"), ("dark", "monokai", "#20252B"))
TOKENS = (("keyword", Keyword), ("comment", Comment), ("string", String))
MIN_RATIO = 4.5


def contrast(foreground: str, background: str) -> float:
    """WCAG 2.1 contrast ratio between two ``#RRGGBB`` colours."""
    def luminance(color: str) -> float:
        out = []
        for offset in (1, 3, 5):
            raw = int(color[offset : offset + 2], 16) / 255.0
            out.append(raw / 12.92 if raw <= 0.03928 else ((raw + 0.055) / 1.055) ** 2.4)
        red, green, blue = out
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    first, second = luminance(foreground), luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def token_colour(style_name: str, token: object) -> str:
    """The style's foreground for one token class (``style_for_token``, not the CSS map)."""
    attrs = get_style_by_name(style_name).style_for_token(token)
    colour = attrs.get("color")
    return f"#{colour}" if colour else "#000000"


def main() -> int:
    from PySide6.QtGui import QImage, QPainter, QTextDocument
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    out_dir = Path(__file__).resolve().parent / "_out"
    out_dir.mkdir(parents=True, exist_ok=True)

    verdict = True
    for label, style_name, code_bg in CANDIDATES:
        print(f"--- {label}: pygments style {style_name!r}, code_bg {code_bg} ---")
        for token_label, token in TOKENS:
            colour = token_colour(style_name, token)
            ratio = contrast(colour, code_bg)
            ok = ratio >= MIN_RATIO
            verdict &= ok
            print(f"  {token_label:<8} {colour}  contrast vs code_bg = {ratio:5.2f}  "
                  f"{'OK' if ok else 'BELOW 4.5'}")

        html = highlight(CODE, PythonLexer(), HtmlFormatter(noclasses=True, nowrap=True,
                                                            style=style_name))
        document = QTextDocument()
        document.setDefaultStyleSheet(f"pre, code {{ background-color: {code_bg}; }}")
        document.setHtml(f'<pre style="background-color:{code_bg}; margin:0;">{html}</pre>')

        image = QImage(int(document.size().width()) + 40, int(document.size().height()) + 20,
                       QImage.Format.Format_RGB32)
        image.fill(code_bg)
        painter = QPainter(image)
        painter.translate(10.0, 10.0)
        document.drawContents(painter)
        painter.end()
        path = out_dir / f"spike_pygments_{label}.png"
        image.save(str(path))

        width, height, stride = image.width(), image.height(), image.bytesPerLine()
        bits = bytes(image.constBits())
        colours = set()
        for y in range(0, height):
            row = bits[y * stride : (y + 1) * stride]
            for offset in range(0, min(len(row), width * 4), 4):
                colours.add((row[offset + 2], row[offset + 1], row[offset]))
        print(f"  rendered {width}x{height}, distinct colours in the raster: {len(colours)}")
        print(f"  -> {path.name}")
        if len(colours) < 3:
            print("  !! fewer than 3 colours: the Qt document did NOT keep the token colours")
            verdict = False

    print(f"\nVERDICT: {'candidates are workable' if verdict else 'needs colour overrides'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
