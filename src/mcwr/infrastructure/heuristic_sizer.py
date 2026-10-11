"""Text-metric size estimator: a cheap, deterministic height guess before rendering."""

from __future__ import annotations

import math
from collections.abc import Mapping

from mcwr.domain.enums import CardKind
from mcwr.domain.models import Block, Card

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
    CardKind.BIG_SECTION: 0.0,
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
            lines += self.lines_for(block.raw_text or block.text_normalized, width)
        lines = max(lines, 1)
        return lines * self._line_height + _EXTRA_HEIGHT.get(card.kind, 0.0)
