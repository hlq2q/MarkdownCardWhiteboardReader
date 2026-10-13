"""Pure invariant checks for a card tree (spec §2.2). Returns problems, never raises."""

from __future__ import annotations

from collections.abc import Collection, Iterable

from mcwr.domain.enums import BlockRole, CardKind, role_of
from mcwr.domain.models import Block, CardTree


def required_block_indexes(blocks: Iterable[Block]) -> frozenset[int]:
    """Indexes that must be owned by some card.

    Thematic breaks are structural only (they separate and are never
    rendered), so they are legitimately owned by nobody; everything else — including
    paragraphs, quotes and plain lists — must survive inside a card (FR-1.3).
    """
    return frozenset(
        block.index for block in blocks if role_of(block.kind) is not BlockRole.DIVIDER
    )


def tree_problems(tree: CardTree, *, required_indexes: Collection[int]) -> tuple[str, ...]:
    """Return every invariant violation found in ``tree``."""
    problems: list[str] = []
    seen: set[str] = set()

    def visit(card_id: str, parent_id: str | None, parent_level: int | None) -> None:
        card = tree.cards.get(card_id)
        if card is None:
            problems.append(f"missing card {card_id}")
            return
        if card_id in seen:
            problems.append(f"card {card_id} reachable more than once")
            return
        seen.add(card_id)
        if card.parent_id != parent_id:
            problems.append(f"card {card_id} parent_id {card.parent_id!r} != {parent_id!r}")
        is_heading = card.kind is CardKind.HEADING
        level = card.level
        if is_heading and level is not None and parent_level is not None and level <= parent_level:
            problems.append(f"heading {card_id} level {level} <= parent {parent_level}")
        for child in card.child_ids:
            visit(child, card_id, card.level if is_heading else None)

    for root in tree.root_ids:
        visit(root, None, None)

    for card_id in tree.cards:
        if card_id not in seen:
            problems.append(f"card {card_id} not reachable from any root")

    covered: list[int] = []
    for card in tree.cards.values():
        covered.extend(card.own_block_indexes)
    duplicates = sorted({index for index in covered if covered.count(index) > 1})
    if duplicates:
        problems.append(f"block indexes owned by several cards: {duplicates}")
    expected = set(required_indexes)
    if set(covered) != expected:
        missing = sorted(expected - set(covered))
        extra = sorted(set(covered) - expected)
        problems.append(f"block coverage mismatch; missing={missing} extra={extra}")

    return tuple(problems)
