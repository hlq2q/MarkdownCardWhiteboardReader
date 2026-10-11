"""Block and card taxonomies plus the single mapping between them.

Every block-level element in a document has a :class:`BlockKind`. Its :class:`BlockRole`
decides what the parse pipeline does with it (spec FR-1.2 / FR-1.3):

* ``CARD``     -> becomes its own card
* ``CONTENT``  -> rendered inside its owning card, never a card itself
* ``DIVIDER``  -> structural only (splits big sections, never rendered)
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Final


class BlockKind(StrEnum):
    """Kind of a block-level element found in the Markdown source."""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    BLOCKQUOTE = "blockquote"
    LIST = "list"
    TASK_LIST = "task_list"
    TABLE = "table"
    CODE = "code"
    MATH_BLOCK = "math_block"
    MERMAID = "mermaid"
    IMAGE = "image"
    TOC = "toc"
    THEMATIC_BREAK = "thematic_break"
    HTML = "html"
    UNKNOWN = "unknown"


class CardKind(StrEnum):
    """Kind of a card shown on the whiteboard."""

    BIG_SECTION = "big_section"
    HEADING = "heading"
    IMAGE = "image"
    CODE = "code"
    TABLE = "table"
    MATH_BLOCK = "math_block"
    MERMAID = "mermaid"
    TASK_LIST = "task_list"
    TOC = "toc"
    FALLBACK_TEXT = "fallback_text"


class BlockRole(StrEnum):
    """What the card builder does with a block."""

    CARD = "card"
    CONTENT = "content"
    DIVIDER = "divider"


CARD_KIND_BY_BLOCK: Final[Mapping[BlockKind, CardKind]] = {
    BlockKind.HEADING: CardKind.HEADING,
    BlockKind.IMAGE: CardKind.IMAGE,
    BlockKind.CODE: CardKind.CODE,
    BlockKind.TABLE: CardKind.TABLE,
    BlockKind.MATH_BLOCK: CardKind.MATH_BLOCK,
    BlockKind.MERMAID: CardKind.MERMAID,
    BlockKind.TASK_LIST: CardKind.TASK_LIST,
    BlockKind.TOC: CardKind.TOC,
}

CONTENT_KINDS: Final[frozenset[BlockKind]] = frozenset(
    {
        BlockKind.PARAGRAPH,
        BlockKind.BLOCKQUOTE,
        BlockKind.LIST,
        BlockKind.HTML,
        BlockKind.UNKNOWN,
    }
)


def role_of(kind: BlockKind) -> BlockRole:
    """Return the pipeline role of ``kind``."""
    if kind in CARD_KIND_BY_BLOCK:
        return BlockRole.CARD
    if kind is BlockKind.THEMATIC_BREAK:
        return BlockRole.DIVIDER
    return BlockRole.CONTENT


def card_kind_for(kind: BlockKind) -> CardKind | None:
    """Return the card kind for a block that becomes a card, else ``None``."""
    return CARD_KIND_BY_BLOCK.get(kind)
