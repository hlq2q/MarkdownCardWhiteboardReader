"""Text-metric size estimator: a cheap, deterministic height guess before rendering."""

from __future__ import annotations

import math
from collections.abc import Mapping

from mcwr.domain.enums import BlockKind, CardKind
from mcwr.domain.models import TOC_ENTRIES_ATTR, Block, Card

_CHAR_WIDTH = 7.6
_LINE_HEIGHT = 20.0
_EXTRA_HEIGHT: dict[CardKind, float] = {
    CardKind.CODE: 16.0,
    CardKind.TABLE: 8.0,
    CardKind.MATH_BLOCK: 24.0,
    CardKind.MERMAID: 40.0,
    CardKind.IMAGE: 120.0,
    CardKind.TASK_LIST: 8.0,
    CardKind.TOC: 8.0,
    CardKind.FALLBACK_TEXT: 0.0,
    CardKind.HEADING: 0.0,
}


class HeuristicSizeEstimator:
    """Wraps text to the card width and multiplies by a line height.

    Deliberately simple and pure: the GUI re-measures after real rendering, and the
    estimate only has to be close enough for a usable initial arrangement.
    """

    def __init__(
        self, *, char_width: float = _CHAR_WIDTH, line_height: float = _LINE_HEIGHT
    ) -> None:
        self._char_width = char_width
        self._line_height = line_height

    def lines_for(self, text: str, width: float) -> int:
        """Number of wrapped lines for ``text`` at ``width`` pixels."""
        chars_per_line = max(int(width / self._char_width), 8)
        explicit = text.splitlines() or [""]
        return sum(max(1, math.ceil(len(line) / chars_per_line)) for line in explicit)

    def estimate_height(self, card: Card, *, blocks: Mapping[int, Block], width: float) -> float:
        """Height of the card's own content (excluding its children and padding)."""
        lines = 0
        for index in card.own_block_indexes:
            block = blocks.get(index)
            if block is None:
                continue
            if block.kind is BlockKind.HEADING:
                # The card's own heading is drawn in the header bar, not in the body -- counting it
                # here made every heading card one line too tall (E-029, measured +20 px), which
                # showed up as a gap between a parent's text and its first child.
                continue
            if card.kind is CardKind.TOC:
                # The card draws the generated entry list, not the one-line ``[TOC]`` marker.
                lines += _toc_lines(block)
                continue
            lines += self.lines_for(block.raw_text or block.text_normalized, width)
        lines = max(lines, 1)
        return lines * self._line_height + _EXTRA_HEIGHT.get(card.kind, 0.0)


def _toc_lines(block: Block) -> int:
    """How many lines a TOC card needs: one per heading (see ``TOC_ENTRIES_ATTR``)."""
    try:
        return max(int(block.attrs.get(TOC_ENTRIES_ATTR, "1")), 1)
    except ValueError:  # a hand-built block may carry anything; fall back to the marker
        return 1
