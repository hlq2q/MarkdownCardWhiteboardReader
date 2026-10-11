"""Detach / restore state machine (FR-4).

Pure operations on the card tree plus the mutable layout mapping: they flip the
``detached`` / ``collapsed`` flags and report what should be re-stacked. Geometry stays
in :mod:`mcwr.application.features.layout_board`, so these functions never compute
coordinates and never touch a file.
"""

from __future__ import annotations

from collections.abc import MutableMapping

from mcwr.application.features.detach_restore.models import ChangeAccumulator, LayoutChange
from mcwr.domain.models import CardId, CardLayout, CardTree


def _require(
    tree: CardTree, layouts: MutableMapping[CardId, CardLayout], card_id: CardId
) -> CardLayout:
    if card_id not in tree.cards:
        raise KeyError(f"unknown card {card_id}")
    layout = layouts.get(card_id)
    if layout is None:
        layout = CardLayout(card_id=card_id)
        layouts[card_id] = layout
    return layout


def can_detach(tree: CardTree, card_id: CardId) -> bool:
    """Only cards that live inside another card can become free cards (FR-4.1)."""
    card = tree.cards.get(card_id)
    return card is not None and card.parent_id is not None


def detach_card(
    tree: CardTree, layouts: MutableMapping[CardId, CardLayout], card_id: CardId
) -> LayoutChange:
    """Mark one card as a free card; its logical parent link is untouched (FR-4.2)."""
    layout = _require(tree, layouts, card_id)
    change = ChangeAccumulator()
    if not can_detach(tree, card_id):
        change.block(card_id, "top-level cards cannot be detached")
        return change.result()
    if layout.detached:
        return change.result()
    layout.detached = True
    change.add(card_id)
    change.relayout = True
    return change.result()


def restore_card(
    tree: CardTree, layouts: MutableMapping[CardId, CardLayout], card_id: CardId
) -> LayoutChange:
    """Put one free card back into its parent, in document order (FR-4.4/4.6)."""
    layout = _require(tree, layouts, card_id)
    change = ChangeAccumulator()
    if not layout.detached:
        change.block(card_id, "card is not a free card")
        return change.result()
    layout.detached = False
    change.add(card_id)
    change.relayout = True
    return change.result()


def reclaim_children(
    tree: CardTree, layouts: MutableMapping[CardId, CardLayout], card_id: CardId
) -> LayoutChange:
    """Restore every free descendant of ``card_id`` ("收回所有子卡片", FR-4.4)."""
    _require(tree, layouts, card_id)
    change = ChangeAccumulator()
    for descendant in tree.descendants(card_id):
        layout = _require(tree, layouts, descendant)
        if layout.detached:
            layout.detached = False
            change.add(descendant)
    change.relayout = bool(change.affected)
    return change.result()


def restore_all(tree: CardTree, layouts: MutableMapping[CardId, CardLayout]) -> LayoutChange:
    """Clear every free card and every fold ("全部还原", FR-4.5).

    Geometry is not computed here: the caller rebuilds the initial arrangement with
    :func:`mcwr.application.features.layout_board.layout_board`.
    """
    change = ChangeAccumulator()
    for card_id in tree.cards:
        layout = _require(tree, layouts, card_id)
        if layout.detached or layout.collapsed:
            change.add(card_id)
        layout.detached = False
        layout.collapsed = False
    change.relayout = True
    return change.result()


def toggle_collapse(
    tree: CardTree, layouts: MutableMapping[CardId, CardLayout], card_id: CardId
) -> LayoutChange:
    """Fold or unfold a card (FR-3.7, decision D6).

    Folding hides the descendants and shrinks the parent; their remembered geometry is
    kept because the layouts of hidden cards are never recomputed here.
    """
    layout = _require(tree, layouts, card_id)
    change = ChangeAccumulator()
    if not tree.cards[card_id].child_ids:
        change.block(card_id, "card has no children to fold")
        return change.result()
    layout.collapsed = not layout.collapsed
    change.add(card_id)
    change.relayout = True
    return change.result()
