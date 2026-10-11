"""Which cards need a web-rendered image, and what exactly gets rendered (D14, R2).

Pure use case: it decides *what* to rasterize and *when* a text fallback is the answer,
but it never touches Qt, WebEngine or the filesystem — the rasterizer is a port. One
canvas transform scales the whole board (D7), so a card that needs KaTeX or Mermaid
contributes a static image instead of a live widget, and the image is per zoom bucket
(see :class:`~mcwr.application.features.render_card.ports.WebCardRenderer`).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Final

from mcwr.application.features.render_card.ports import WebCardRenderer
from mcwr.domain.enums import CardKind
from mcwr.domain.models import Block, Card

WEB_RENDER_KINDS: Final[frozenset[CardKind]] = frozenset(
    {CardKind.MATH_BLOCK, CardKind.MERMAID}
)
"""Card kinds whose content only a browser engine can draw (KaTeX / Mermaid bundle)."""

_MATH_DELIMITERS: Final[tuple[tuple[str, str], ...]] = (
    ("$$", "$$"),
    (r"\[", r"\]"),
    (r"\(", r"\)"),
    ("$", "$"),
)
"""Display-math wrappers stripped before KaTeX sees the body, most specific first."""


def needs_web_render(card: Card) -> bool:
    """Whether this card's own content has to be rasterized to be readable."""
    return card.kind in WEB_RENDER_KINDS


def web_source(card: Card, blocks: Mapping[int, Block], index: int) -> str | None:
    """The exact source to render: the LaTeX body for math, the diagram source for mermaid.

    ``blocks`` is the document IR keyed by :attr:`Block.index`. The returned string is what
    the renderer feeds to KaTeX/Mermaid, so for math the ``$$`` fences are gone and for
    Mermaid the fence lines and the ``mermaid`` info string are gone. ``None`` means "there
    is nothing to rasterize here" (wrong kind, no such block, or an empty body).
    """
    if not needs_web_render(card):
        return None
    block = _source_block(card, blocks, index)
    if block is None:
        return None
    body = (
        _strip_math_fences(block.raw_text)
        if card.kind is CardKind.MATH_BLOCK
        else _strip_mermaid_fence(block.raw_text)
    )
    return body or None


def card_image(
    card: Card,
    blocks: Mapping[int, Block],
    *,
    renderer: WebCardRenderer,
    scale: float,
) -> Path | None:
    """Convenience for the view: the cached PNG for ``card``, or ``None``.

    ``None`` means "draw the card as text" — either the card needs no image at all, or
    rendering failed (the renderer records why, so the GUI can show a warning).
    """
    source = web_source(card, blocks, card.block_index if card.block_index is not None else -1)
    if source is None:
        return None
    return renderer.render(kind=card.kind, source=source, scale=scale)


def _source_block(card: Card, blocks: Mapping[int, Block], index: int) -> Block | None:
    """The block holding this card's math/diagram source.

    ``index`` is the caller's best guess (usually :attr:`Card.block_index`); a card whose
    primary block is missing falls back to the first own block that carries content.
    """
    for candidate in (index, *card.own_block_indexes):
        block = blocks.get(candidate)
        if block is not None and block.raw_text.strip():
            return block
    return None


def _strip_math_fences(raw_text: str) -> str:
    """Reduce Markdown display math to the LaTeX body KaTeX understands."""
    text = raw_text.strip()
    for opener, closer in _MATH_DELIMITERS:
        if not (text.startswith(opener) and text.endswith(closer)):
            continue
        body = text[len(opener) : len(text) - len(closer)]
        if len(text) <= len(opener) + len(closer):
            continue
        # A single-character fence ($x$) only counts when the body holds no fence of its
        # own, so prose like "$5 and $6" is left alone instead of rendered as math.
        if len(opener) == 1 and opener in body:
            continue
        return body.strip()
    return text


def _strip_mermaid_fence(raw_text: str) -> str:
    """Drop the ```` ```mermaid ````/```` ``` ```` fence, keeping the diagram body verbatim."""
    lines = raw_text.strip().splitlines()
    if len(lines) >= 2 and lines[0].lstrip().startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return raw_text.strip()
