"""Card-tree construction: blocks (IR) -> heading nesting (spec §2.3, D-056).

A top-level heading is a root, content before the first heading becomes a card of its own, and a
thematic break only separates -- there is no section wrapper card any more (T-055)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from mcwr.domain.enums import BlockKind, BlockRole, CardKind, card_kind_for, role_of
from mcwr.domain.ids import content_hash, stable_key
from mcwr.domain.models import Block, Card, CardId, CardTree

_DEFAULT_TITLE: dict[CardKind, str] = {
    CardKind.TABLE: "table",
    CardKind.MATH_BLOCK: "math",
    CardKind.MERMAID: "mermaid",
    CardKind.TASK_LIST: "tasks",
    CardKind.TOC: "TOC",
    CardKind.FALLBACK_TEXT: "text",
    CardKind.CODE: "code",
}


@dataclass(slots=True)
class _Node:
    """Mutable accumulator; turned into a frozen :class:`Card` at the end."""

    kind: CardKind
    level: int | None
    heading_text: str
    heading_path: tuple[str, ...]
    parent: int | None = None
    primary_block: int | None = None
    blocks: list[int] = field(default_factory=list)
    raw_parts: list[str] = field(default_factory=list)
    children: list[int] = field(default_factory=list)
    ordinal_in_parent: int = 0
    occurrence: int = 0
    title: str = ""


def _title_for(node: _Node, block: Block | None) -> str:
    if node.kind is CardKind.HEADING:
        return node.heading_text
    if node.kind is CardKind.CODE and block is not None and block.lang:
        return block.lang
    if node.kind is CardKind.IMAGE and block is not None:
        return block.attrs.get("alt") or block.attrs.get("src", "") or "image"
    return _DEFAULT_TITLE.get(node.kind, node.kind.value)


class _Builder:
    """Collects nodes for one document and assigns sibling ordinals."""

    def __init__(self) -> None:
        self.nodes: list[_Node] = []
        self.roots: list[int] = []

    def add(self, node: _Node) -> int:
        self.nodes.append(node)
        return len(self.nodes) - 1

    def attach(self, parent_index: int, node: _Node) -> int:
        """Append ``node`` under ``parent_index`` and assign ordinal/occurrence."""
        parent = self.nodes[parent_index]
        node.parent = parent_index
        node.ordinal_in_parent = len(parent.children)
        node.occurrence = sum(
            1 for child in parent.children if _same_identity(self.nodes[child], node)
        )
        child_index = self.add(node)
        parent.children.append(child_index)
        return child_index

    def attach_root(self, node: _Node) -> int:
        """Append ``node`` as a root, with exactly the ordinal/occurrence rules ``attach`` uses.

        The roots are siblings like any others, which is what keeps a heading card's stable id the
        same as it was when a section wrapper stood above it (T-055).
        """
        node.parent = None
        node.ordinal_in_parent = len(self.roots)
        node.occurrence = sum(1 for root in self.roots if _same_identity(self.nodes[root], node))
        index = self.add(node)
        self.roots.append(index)
        return index


def _same_identity(left: _Node, right: _Node) -> bool:
    """Siblings are the "same" for occurrence counting only when they collide by name."""
    if left.kind is not right.kind:
        return False
    if left.kind is CardKind.HEADING:
        return left.heading_text == right.heading_text
    return left.heading_path == right.heading_path


def _loose_node(block: Block, card_kind: CardKind = CardKind.FALLBACK_TEXT) -> _Node:
    """A card for content that stands outside any heading (it used to belong to a section).

    The block only supplies the card's identity: the walk appends every block the card owns, so
    lists here would claim it twice.
    """
    return _Node(
        kind=card_kind,
        level=None,
        heading_text="",
        heading_path=(),
        primary_block=block.index,
    )


def _card_node(block: Block, card_kind: CardKind, parent: _Node) -> _Node:
    return _Node(
        kind=card_kind,
        level=None,
        heading_text="",
        heading_path=parent.heading_path,
        primary_block=block.index,
        blocks=[block.index],
        raw_parts=[block.raw_text],
    )


def _heading_node(block: Block, level: int, parent: _Node | None) -> _Node:
    text = block.text_normalized or f"H{level}"
    return _Node(
        kind=CardKind.HEADING,
        level=level,
        heading_text=text,
        heading_path=(*parent.heading_path, text) if parent is not None else (text,),
        primary_block=block.index,
        blocks=[block.index],
        raw_parts=[block.raw_text],
    )


def _build_cards(builder: _Builder, blocks: Sequence[Block]) -> None:
    """Walk the document once: an empty stack means the next heading is a root (T-055/D-056).

    Content seen while no heading is open becomes a card of its own rather than being owned by a
    synthetic section, and a thematic break is skipped entirely: it only separates.
    """
    stack: list[int] = []
    loose_index: int | None = None

    for block in blocks:
        if block.kind is BlockKind.THEMATIC_BREAK:
            continue
        role = role_of(block.kind)
        if role is BlockRole.CONTENT:
            if stack:
                owner = builder.nodes[stack[-1]]
            else:
                if loose_index is None:
                    loose_index = builder.attach_root(_loose_node(block))
                owner = builder.nodes[loose_index]
            owner.blocks.append(block.index)
            owner.raw_parts.append(block.raw_text)
            continue
        if role is not BlockRole.CARD:
            continue
        card_kind = card_kind_for(block.kind)
        if card_kind is None:  # pragma: no cover - role_of already gates this
            continue
        if card_kind is not CardKind.HEADING:
            if stack:
                owner = builder.nodes[stack[-1]]
                builder.attach(stack[-1], _card_node(block, card_kind, owner))
            else:
                # a card block with no heading above it is a root of its own, and it owns its block
                node = _loose_node(block, card_kind)
                node.blocks.append(block.index)
                node.raw_parts.append(block.raw_text)
                builder.attach_root(node)
            continue

        level = block.level or 1
        while stack and (builder.nodes[stack[-1]].level or 7) >= level:
            stack.pop()
        if stack:
            parent = builder.nodes[stack[-1]]
            stack.append(builder.attach(stack[-1], _heading_node(block, level, parent)))
        else:
            stack.append(builder.attach_root(_heading_node(block, level, None)))
        loose_index = None  # a new heading chain collects its own loose content


def _materialize(
    builder: _Builder, path_hash: str, by_index: dict[int, Block]
) -> tuple[dict[CardId, Card], dict[int, CardId]]:
    """Freeze accumulated nodes into cards keyed by their stable key."""
    ids: dict[int, CardId] = {
        index: stable_key(
            path_hash=path_hash,
            heading_path=node.heading_path,
            card_kind=node.kind,
            ordinal_in_parent=node.ordinal_in_parent,
            occurrence=node.occurrence,
        )
        for index, node in enumerate(builder.nodes)
    }
    cards: dict[CardId, Card] = {}
    for index, node in enumerate(builder.nodes):
        primary = by_index.get(node.primary_block) if node.primary_block is not None else None
        cards[ids[index]] = Card(
            card_id=ids[index],
            kind=node.kind,
            parent_id=ids[node.parent] if node.parent is not None else None,
            child_ids=tuple(ids[child] for child in node.children),
            own_block_indexes=tuple(node.blocks),
            heading_path=node.heading_path,
            ordinal_in_parent=node.ordinal_in_parent,
            occurrence=node.occurrence,
            content_hash=content_hash("\n\n".join(node.raw_parts)),
            title=_title_for(node, primary),
            block_index=node.primary_block,
            level=node.level,
        )
    return cards, ids


def build_card_tree(blocks: Sequence[Block], *, path_hash: str) -> CardTree:
    """Build the card tree for one parsed document.

    ``path_hash`` comes from :func:`mcwr.domain.ids.document_path_hash` and only
    distinguishes documents; it never depends on content.
    """
    builder = _Builder()
    _build_cards(builder, blocks)
    cards, ids = _materialize(builder, path_hash, {block.index: block for block in blocks})
    return CardTree(cards=cards, root_ids=tuple(ids[index] for index in builder.roots))
