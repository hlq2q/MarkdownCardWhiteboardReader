"""T-029 at the window level: a code card really paints more than one text colour.

The unit tests pin which colours the highlighter produces; this one paints the card and
counts the colours that reach the raster, so a regression that silently drops the
highlighting (a card drawn in one text colour) fails here even when the HTML still looks
right in a string comparison.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QStyleOptionGraphicsItem

from mcwr.domain.enums import CardKind
from mcwr.interfaces.gui.card_item import CardItem
from mcwr.interfaces.gui.main_window import MainWindow
from mcwr.interfaces.gui.theme import DARK, LIGHT, ThemeMode

DOCUMENT = '''# Code

```python
def slug(text: str) -> str:
    """Lower-case a title."""
    # punctuation goes away
    return "-".join(text.casefold().split())
```

```text
plain block with no language
```
'''

CHANNEL_TOLERANCE = 24


class StubRenderer:
    last_error = None

    def render(
        self, *, kind: object, source: str, scale: float, theme: str = "light"
    ) -> Path | None:
        del kind, source, scale, theme
        return None


def _open(tmp_path: Path) -> MainWindow:
    document = tmp_path / "code.md"
    document.write_text(DOCUMENT, encoding="utf-8")
    window = MainWindow(persist=False, renderer=StubRenderer())  # type: ignore[arg-type]
    assert window.open_path(document) is True
    return window


def _code_item(window: MainWindow, lang: str) -> CardItem:
    for item in window.card_items.values():
        if item.card.kind is not CardKind.CODE:
            continue
        block = window.session.blocks.get(item.card.block_index or -1)
        if block is not None and block.lang == lang:
            return item
    raise AssertionError(f"no code card with lang={lang!r} on the board")


def _paint(item: CardItem) -> QImage:
    image = QImage(int(item.card_width), int(item.card_height), QImage.Format.Format_RGB32)
    image.fill(0)
    painter = QPainter(image)
    item.paint(painter, QStyleOptionGraphicsItem(), None)
    painter.end()
    return image


def _body_colours(item: CardItem, ignored: tuple[str, ...]) -> set[tuple[int, int, int]]:
    """Colours inside the body that differ from the fill and the base text colour.

    Quantised comparison with a tolerance, because antialiased glyph edges blend the text
    colour into the background.
    """
    image = _paint(item)
    body = item.body_rect()
    stride = image.bytesPerLine()
    bits = bytes(image.constBits())
    skip = [QColor(colour).getRgb()[:3] for colour in ignored]
    found: set[tuple[int, int, int]] = set()
    for y in range(int(body.top()) + 1, int(body.bottom()), 2):
        row = bits[y * stride : (y + 1) * stride]
        for offset in range(int(body.left()) * 4, min(len(row), int(body.right()) * 4), 8):
            pixel = (row[offset + 2], row[offset + 1], row[offset])
            far_from_every_ignored = all(
                any(
                    abs(pixel[channel] - other[channel]) > CHANNEL_TOLERANCE for channel in range(3)
                )
                for other in skip
            )
            if far_from_every_ignored:
                found.add(pixel)
    return found


def test_a_python_code_card_paints_several_colours_in_both_themes(tmp_path: Path) -> None:
    window = _open(tmp_path)
    for mode, palette in ((ThemeMode.LIGHT, LIGHT), (ThemeMode.DARK, DARK)):
        window.apply_theme(mode)
        highlighted = _body_colours(
            _code_item(window, "python"), (palette.code_bg, palette.text_primary)
        )
        plain = _body_colours(_code_item(window, "text"), (palette.code_bg, palette.text_primary))
        assert len(highlighted) >= 2, f"{palette.theme}: only {highlighted} in the body"
        assert len(plain) < len(highlighted), (
            f"{palette.theme}: a plain block must not look as colourful as a highlighted one"
        )


def test_the_code_card_shows_the_code_without_its_fence(tmp_path: Path) -> None:
    """E-022: the fence is Markdown syntax, not content — the card must not draw it."""
    window = _open(tmp_path)
    text = _code_item(window, "python")._document.toPlainText()
    assert "```" not in text
    assert "~~~" not in text
    assert "def slug" in text, "the code itself must still be there"


def test_the_two_themes_paint_the_same_code_card_differently(tmp_path: Path) -> None:
    window = _open(tmp_path)
    window.apply_theme(ThemeMode.LIGHT)
    light = _paint(_code_item(window, "python"))
    window.apply_theme(ThemeMode.DARK)
    dark = _paint(_code_item(window, "python"))
    assert bytes(light.constBits()) != bytes(dark.constBits()), (
        "switching the theme must repaint the code with the other style"
    )
