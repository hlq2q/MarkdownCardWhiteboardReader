"""CLI presentation helpers: turn a loaded document into JSON or an outline."""

from __future__ import annotations

from typing import Any

from mcwr.application.features.load_document.models import LoadedDocument
from mcwr.domain.models import CardTree


def tree_to_dict(loaded: LoadedDocument) -> dict[str, Any]:
    """Machine-readable view of a loaded document (stable key order for diffing)."""
    tree = loaded.tree
    return {
        "document": {
            "path": str(loaded.document.path),
            "path_hash": loaded.document.path_hash,
            "size": loaded.document.size,
            "mtime": loaded.document.mtime,
            "content_hash": loaded.document.content_hash,
        },
        "warnings": list(loaded.warnings),
        "blocks": [
            {
                "index": block.index,
                "kind": str(block.kind),
                "level": block.level,
                "lang": block.lang,
                "span": None
                if block.span is None
                else [block.span.start_line, block.span.end_line],
                "text": block.text_normalized[:200],
            }
            for block in loaded.blocks
        ],
        "cards": [card_to_dict(tree, card_id) for card_id in tree.ordered_ids()],
    }


def card_to_dict(tree: CardTree, card_id: str) -> dict[str, Any]:
    card = tree.cards[card_id]
    return {
        "id": card.card_id,
        "kind": str(card.kind),
        "title": card.title,
        "parent": card.parent_id,
        "children": list(card.child_ids),
        "heading_path": list(card.heading_path),
        "level": card.level,
        "blocks": list(card.own_block_indexes),
        "content_hash": card.content_hash,
        "depth": len(tree.ancestors(card_id)),
    }


def render_outline(loaded: LoadedDocument) -> str:
    """Human-readable tree, one card per line, indented by nesting depth."""
    tree = loaded.tree
    lines: list[str] = []
    for card_id in tree.ordered_ids():
        card = tree.cards[card_id]
        depth = len(tree.ancestors(card_id))
        blocks = len(card.own_block_indexes)
        marker = f"[{card.kind}]"
        tail = f"  blocks={blocks}" if blocks else ""
        lines.append(f"{'  ' * depth}{marker} {card.title}{tail}")
    header = f"{loaded.document.path}  cards={len(tree.cards)} blocks={len(loaded.blocks)}"
    return "\n".join([header, *lines])
