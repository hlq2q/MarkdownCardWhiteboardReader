"""Initial layout: stack cards top-to-bottom in document order (FR-3.1).

The whiteboard coordinate system is the single source of geometric truth: every card
stores absolute coordinates, so detaching a card never needs a coordinate conversion.
A card's box holds its own content first and its children below, so the initial
arrangement reads exactly like the source document while still nesting.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from mcwr.application.features.layout_board.ports import SizeEstimator
from mcwr.domain.models import Block, Card, CardId, CardLayout, CardTree

_MIN_INNER_WIDTH = 80.0


@dataclass(frozen=True, slots=True)
class LinearLayoutOptions:
    """Spacing defaults for the initial arrangement (tunable, not user-visible yet).

    Tightened in T-050 on the user's call: a parent's text ended too far above its first child. The
    gap between a body's bottom and the next box was 40 px (12 bottom padding + trailing leading +
    16 sibling gap) and is now about 28 px (6 + leading + 8).
    """

    section_width: float = 960.0
    indent: float = 24.0
    gap: float = 8.0
    padding: float = 6.0
    header_height: float = 34.0
    min_height: float = 56.0


class _Placer:
    """Recursive placement; writes into ``layouts`` and returns the height used.

    ``states`` carries the current view state so a re-layout keeps a collapsed card
    collapsed and never pulls a detached card back inside its parent (FR-3.7, FR-4.2).
    """

    def __init__(
        self,
        tree: CardTree,
        blocks: Mapping[int, Block],
        estimator: SizeEstimator,
        options: LinearLayoutOptions,
        states: Mapping[CardId, CardLayout] | None = None,
    ) -> None:
        self._tree = tree
        self._blocks = blocks
        self._estimator = estimator
        self._options = options
        self._states = states
        self.layouts: dict[CardId, CardLayout] = {}

    def state_of(self, card_id: CardId) -> CardLayout | None:
        return None if self._states is None else self._states.get(card_id)

    def is_detached(self, card_id: CardId) -> bool:
        state = self.state_of(card_id)
        return bool(state is not None and state.detached)

    def children_to_place(self, card: Card) -> tuple[CardId, ...]:
        """Children that live inside this card right now (collapse/detach aware)."""
        state = self.state_of(card.card_id)
        if state is not None and state.collapsed:
            return ()
        return tuple(child for child in card.child_ids if not self.is_detached(child))

    def place(self, card_id: CardId, *, x: float, y: float, width: float, depth: int) -> float:
        """Place ``card_id`` and its subtree, returning the card's height."""
        card = self._tree.cards[card_id]
        inner_width = max(width - 2 * self._options.padding, _MIN_INNER_WIDTH)
        header = 0.0 if card.is_big_section else self._options.header_height
        own_height = (
            header
            + self._estimator.estimate_height(card, blocks=self._blocks, width=inner_width)
            + 2 * self._options.padding
        )
        children_height = self._place_children(
            self.children_to_place(card),
            x=x + self._options.indent,
            y=y + own_height + self._options.gap,
            width=max(width - 2 * self._options.indent, _MIN_INNER_WIDTH),
            depth=depth,
        )
        height = max(own_height + children_height, self._options.min_height)
        previous = self.state_of(card_id)
        layout = CardLayout(
            card_id=card_id,
            x=x,
            y=y,
            width=width,
            height=height,
            z=depth,
            collapsed=previous.collapsed if previous else False,
            detached=previous.detached if previous else False,
            manual_size=previous.manual_size if previous else False,
        )
        self.layouts[card_id] = layout
        return height

    def _place_children(
        self, child_ids: tuple[CardId, ...], *, x: float, y: float, width: float, depth: int
    ) -> float:
        total = 0.0
        for index, child_id in enumerate(child_ids):
            child_height = self.place(child_id, x=x, y=y + total, width=width, depth=depth + 1)
            total += child_height
            if index < len(child_ids) - 1:
                total += self._options.gap
        return self._options.gap + total if child_ids else 0.0


def layout_board(
    tree: CardTree,
    *,
    blocks: Mapping[int, Block],
    estimator: SizeEstimator,
    options: LinearLayoutOptions | None = None,
) -> dict[CardId, CardLayout]:
    """Return a fresh attached layout for every card in ``tree``, in document order."""
    resolved = options or LinearLayoutOptions()
    placer = _Placer(tree, blocks, estimator, resolved)
    cursor = 0.0
    for root_id in tree.root_ids:
        height = placer.place(root_id, x=0.0, y=cursor, width=resolved.section_width, depth=0)
        cursor += height + resolved.gap
    return placer.layouts


def relayout_subtree(
    tree: CardTree,
    layouts: Mapping[CardId, CardLayout],
    card_id: CardId,
    *,
    blocks: Mapping[int, Block],
    estimator: SizeEstimator,
    options: LinearLayoutOptions | None = None,
) -> dict[CardId, CardLayout]:
    """Re-stack one card and its descendants in place, keeping every other card.

    Used after collapse/expand, detach/restore and reclaim: cards that stay attached
    keep their x/y, while the affected subtree is packed again from its own top-left
    corner. Detached descendants are left where the user put them.
    """
    resolved = options or LinearLayoutOptions()
    base = layouts.get(card_id)
    if base is None:
        raise KeyError(f"no layout for card {card_id}")
    placer = _Placer(tree, blocks, estimator, resolved, states=layouts)
    placer.place(card_id, x=base.x, y=base.y, width=base.width, depth=base.z)
    merged = dict(layouts)
    merged.update(placer.layouts)
    return merged
