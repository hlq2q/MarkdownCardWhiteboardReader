"""Syntax highlighting for code cards (T-029): Pygments tokens → inline-coloured HTML.

This is the **only** module that imports Pygments. ``application``/``domain`` must stay free
of concrete libraries (``tests/integration/test_render_stability.py`` scans for that), and
the GUI only ever receives a ready-to-render HTML fragment.

Colour policy — measured, not guessed (`spikes/spike_pygments_qt.py`, `spikes/NOTES.md`):

* the style name comes from the active palette (``theme.Palette.pygments_style``);
* a token whose style colour does not clear :data:`~mcwr.shared.contrast.MIN_RATIO_AA`
  against the code background falls back to the palette's ``text_secondary``. That slot is
  already AA-verified, so no colour is invented here and no token can become unreadable in
  either theme — the light ``default`` style, for instance, paints comments in ``#3D7B7B``,
  which is only 4.41:1 on the spec's ``code_bg``.
"""

from __future__ import annotations

import html
from typing import Any, Final

from pygments import lex
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.styles import get_style_by_name
from pygments.util import ClassNotFound

from mcwr.shared.contrast import MIN_RATIO_AA, contrast_ratio

SPAN_TEMPLATE: Final[str] = '<span style="color:{colour}">{text}</span>'
"""One coloured run; Qt's rich text supports ``color`` on a span (verified by the spike)."""


def token_runs(code: str, lang: str | None) -> tuple[tuple[Any, str], ...]:
    """Lex ``code`` into ``(token_type, text)`` pairs.

    An unknown or missing language degrades to :class:`TextLexer` (plain runs) instead of
    raising: a code card must always render (FR-1.5).
    """
    lexer = TextLexer()
    if lang:
        try:
            lexer = get_lexer_by_name(lang)
        except ClassNotFound:
            lexer = TextLexer()
    runs: list[tuple[Any, str]] = []
    for token_type, text in lex(code, lexer):
        runs.append((token_type, str(text)))
    return tuple(runs)


def highlight_html(
    code: str, lang: str | None, *, style: str, background: str, fallback: str
) -> str:
    """Inline-coloured HTML for one code block: no ``<pre>`` wrapper, escaped text.

    ``background`` is the code background the colours must be readable on; ``fallback`` is
    the colour used when the style's own colour fails :data:`MIN_RATIO_AA` (see the module
    docstring). Tokens the style leaves uncoloured stay uncoloured and inherit the card's
    text colour. An empty or whitespace-only block yields ``""``: Pygments would otherwise
    hand back the newline it appends, which is a coloured run with nothing in it.
    """
    if not code.strip():
        return ""
    pieces: list[str] = []
    for token_type, text in token_runs(code, lang):
        escaped = html.escape(text)
        colour = _resolved_colour(style, token_type, background, fallback)
        if colour is None:
            pieces.append(escaped)
        else:
            pieces.append(SPAN_TEMPLATE.format(colour=colour, text=escaped))
    return "".join(pieces)


def _resolved_colour(style: str, token_type: Any, background: str, fallback: str) -> str | None:
    """Colour for one token run, the fallback when it is unreadable, or ``None`` to inherit."""
    raw: str | None = get_style_by_name(style).style_for_token(token_type).get("color")
    if not raw:
        return None
    colour = f"#{raw}"
    return fallback if contrast_ratio(colour, background) < MIN_RATIO_AA else colour
