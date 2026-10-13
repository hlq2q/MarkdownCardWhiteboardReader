"""Tests for the code highlighter (T-029): lexing, escaping and the contrast floor.

The colour assertions are the point: the spike measured that the light ``default`` style
paints comments at 4.41:1 on the spec's ``code_bg``, so the highlighter must substitute the
palette's AA-verified ``text_secondary`` for exactly those tokens — and every colour that
reaches the card must clear the floor in *both* themes.
"""

from __future__ import annotations

import html
import re

from mcwr.infrastructure.pygments_highlighter import highlight_html, token_runs
from mcwr.interfaces.gui.theme import DARK, LIGHT, Palette
from mcwr.shared.contrast import MIN_RATIO_AA, contrast_ratio

CODE = '''def slug(text: str) -> str:
    """Lower-case a title."""
    # punctuation goes away
    return "-".join(text.casefold().split())
'''

COLOUR_RE = re.compile(r"color:(#[0-9A-Fa-f]{6})")
LIGHT_COMMENT = "#3d7b7b"
"""The ``default`` style's comment colour: the one the spike measured below 4.5:1."""


def _colours(markup: str) -> set[str]:
    return {colour.lower() for colour in COLOUR_RE.findall(markup)}


def _highlight(palette: Palette, code: str = CODE, lang: str | None = "python") -> str:
    return highlight_html(
        code,
        lang,
        style=palette.pygments_style,
        background=palette.code_bg,
        fallback=palette.text_secondary,
    )


def test_python_code_lexes_into_several_token_runs() -> None:
    runs = token_runs(CODE, "python")
    assert len(runs) > 3
    assert "".join(text for _, text in runs) == CODE, "lexing must not lose or reorder text"


def test_both_themes_colour_the_code_differently() -> None:
    light = _colours(_highlight(LIGHT))
    dark = _colours(_highlight(DARK))
    assert len(light) >= 3 and len(dark) >= 3, (light, dark)
    assert light != dark
    assert "#008000" in light, "the light style's keyword colour"
    assert "#66d9ef" in dark, "the dark style's keyword colour"


def test_every_colour_that_reaches_the_card_clears_the_contrast_floor() -> None:
    for palette in (LIGHT, DARK):
        for colour in _colours(_highlight(palette)):
            ratio = contrast_ratio(colour, palette.code_bg)
            assert ratio >= MIN_RATIO_AA, (palette.theme, colour, round(ratio, 2))


def test_the_unreadable_light_comment_colour_is_replaced_by_the_theme_slot() -> None:
    markup = _highlight(LIGHT)
    colours = _colours(markup)
    assert LIGHT_COMMENT not in colours, "the 4.41:1 comment colour must not be used"
    assert LIGHT.text_secondary.lower() in colours, "the fallback slot must be used instead"
    assert markup.count(LIGHT.text_secondary) >= 1


def test_the_dark_theme_keeps_the_styles_own_comment_colour() -> None:
    """The override is a floor, not a blanket rule: monokai's comment already passes."""
    assert "#959077" in _colours(_highlight(DARK))


def test_an_unknown_language_degrades_to_plain_text() -> None:
    """No lexer means one plain run — escaped, but with no coloured spans."""
    assert _highlight(LIGHT, lang="not-a-language") == html.escape(CODE)
    assert _highlight(LIGHT, code="plain\n", lang=None) == "plain\n"
    assert "span" not in _highlight(LIGHT, code="plain\n", lang=None)


def test_markup_in_the_code_is_escaped() -> None:
    markup = _highlight(LIGHT, code='x = "<script>alert(1)</script>"\n', lang="python")
    assert "<script>" not in markup
    assert "&lt;script&gt;" in markup
    assert "&amp;" in markup or "&quot;" in markup


def test_an_empty_block_produces_nothing() -> None:
    assert _highlight(LIGHT, code="") == ""
