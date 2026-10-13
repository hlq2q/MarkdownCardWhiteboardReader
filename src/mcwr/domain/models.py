"""Pure domain models: blocks (IR), cards, layout state and the persisted snapshot.

Nothing here performs IO or imports a framework. Mutable dataclasses are limited to
layout/view state, which the UI edits in place; everything else is frozen.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Final

from mcwr.domain.enums import BlockKind, CardKind

CardId = str
"""Card identity: the ``stable_key`` digest (see :mod:`mcwr.domain.ids`)."""

SNAPSHOT_SCHEMA_VERSION: Final[int] = 1

MAX_CARDS: Final[int] = 1000
"""Largest document we lay out with rich content (D-023 value, raised by D-040).

A document with more cards is still opened, but the offscreen math/diagram rendering is
switched off and those cards keep their source text (decision D-029). The value was 200 while
every math/Mermaid card in the document was rasterized on open; since viewport lazy loading
(D-040, NFR-3) only what is on screen is rendered, a much larger document stays comfortable.
"""

TOC_ENTRIES_ATTR: Final[str] = "toc_entries"
"""``Block.attrs`` key: how many headings a ``[TOC]`` block will list as clickable entries.

Stamped by the parser, which is the only place that sees the whole document: the size
estimator receives one card's own block and could not count the headings itself.
"""


# --------------------------------------------------------------------------- blocks


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """Inclusive line range in the source file."""

    start_line: int
    end_line: int

    def __post_init__(self) -> None:
        if self.start_line < 1 or self.end_line < self.start_line:
            raise ValueError(f"invalid source span: {self.start_line}..{self.end_line}")


@dataclass(frozen=True, slots=True)
class InlineSpan:
    """An inline element kept for rendering inside a card (bold, link, inline code, math)."""

    kind: str
    text: str
    target: str | None = None


@dataclass(frozen=True, slots=True)
class Block:
    """One block-level element of the document — the single intermediate truth."""

    index: int
    kind: BlockKind
    raw_text: str
    text_normalized: str
    level: int | None = None
    lang: str | None = None
    inline: tuple[InlineSpan, ...] = ()
    span: SourceSpan | None = None
    attrs: Mapping[str, str] = field(default_factory=dict)

    @property
    def title(self) -> str:
        """Best-effort one-line title (truncated) used by card chrome."""
        return self.text_normalized[:80]


# ---------------------------------------------------------------------------- cards


@dataclass(frozen=True, slots=True)
class Card:
    """A card in the tree. Geometry lives in :class:`CardLayout`, not here."""

    card_id: CardId
    kind: CardKind
    parent_id: CardId | None
    child_ids: tuple[CardId, ...]
    own_block_indexes: tuple[int, ...]
    heading_path: tuple[str, ...]
    ordinal_in_parent: int
    occurrence: int
    content_hash: str
    title: str
    block_index: int | None = None
    level: int | None = None


@dataclass(frozen=True, slots=True)
class CardTree:
    """Cards plus the roots, in document order."""

    cards: Mapping[CardId, Card]
    root_ids: tuple[CardId, ...]

    def ordered_ids(self) -> tuple[CardId, ...]:
        """Depth-first document order starting from the roots."""
        out: list[CardId] = []

        def walk(card_id: CardId) -> None:
            out.append(card_id)
            for child in self.cards[card_id].child_ids:
                walk(child)

        for root in self.root_ids:
            walk(root)
        return tuple(out)

    def ancestors(self, card_id: CardId) -> tuple[CardId, ...]:
        """Ancestors from the immediate parent up to the root."""
        chain: list[CardId] = []
        current = self.cards[card_id].parent_id
        while current is not None:
            chain.append(current)
            current = self.cards[current].parent_id
        return tuple(chain)

    def descendants(self, card_id: CardId) -> tuple[CardId, ...]:
        """All descendants in depth-first order, excluding ``card_id`` itself."""
        out: list[CardId] = []
        stack = list(reversed(self.cards[card_id].child_ids))
        while stack:
            current = stack.pop()
            out.append(current)
            stack.extend(reversed(self.cards[current].child_ids))
        return tuple(out)


# --------------------------------------------------------------------------- layout


@dataclass(slots=True)
class CardLayout:
    """Geometry and view state of one card, in whiteboard coordinates."""

    card_id: CardId
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    z: int = 0
    collapsed: bool = False
    detached: bool = False
    manual_size: bool = False
    scale: float = 1.0
    """Resize factor of this card's own subtree (T-057): 1.0 is the natural size."""

    effective_scale: float = 1.0
    """``scale`` times every ancestor's scale: the number the view draws with (T-064)."""

    def move_to(self, x: float, y: float) -> None:
        self.x = x
        self.y = y

    def resize_to(self, width: float, height: float, *, manual: bool = True) -> None:
        self.width = width
        self.height = height
        self.manual_size = manual


@dataclass(slots=True)
class Viewport:
    """Canvas transform state (decision D7: one transform scales cards and text)."""

    scale: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0
    fitted_once: bool = False

    # ClassVar so dataclasses does not turn these bounds into fields.
    MIN_SCALE: ClassVar[float] = 0.1
    MAX_SCALE: ClassVar[float] = 8.0

    def set_scale(self, scale: float) -> None:
        self.scale = min(max(scale, self.MIN_SCALE), self.MAX_SCALE)


@dataclass(slots=True)
class WindowState:
    """Per-window state persisted under ``windows/<window_uuid>.json``."""

    window_uuid: str
    x: int = 0
    y: int = 0
    width: int = 1280
    height: int = 800
    maximized: bool = False
    open_documents: tuple[str, ...] = ()
    active_document: str | None = None


class LayoutScope(StrEnum):
    """Which slice of a board snapshot is being read or written."""

    SESSION = "session"
    PROBE = "probe"


@dataclass(frozen=True, slots=True)
class DocumentKey:
    """Identifies one read of one document (FR-7.3)."""

    path: Path
    path_hash: str
    size: int
    mtime: float
    content_hash: str


@dataclass(slots=True)
class BoardSnapshot:
    """The persisted unit for one document and one session (decisions D9 + D15)."""

    schema_version: int
    document: DocumentKey
    layouts: dict[CardId, CardLayout] = field(default_factory=dict)
    viewport: Viewport = field(default_factory=Viewport)
    window_uuid: str = ""
