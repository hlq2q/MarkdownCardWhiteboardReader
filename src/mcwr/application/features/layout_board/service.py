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
from mcwr.domain.enums import BlockKind
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
    # T-060: halved from 24, so a child card sits 12 px inside its parent on the left *and* the
    # right (the child's width is the box minus two indents).
    indent: float = 8.0
    gap: float = 8.0
    padding: float = 6.0
    header_height: float = 22.7
    min_height: float = 56.0


def _ancestor_scale(tree: CardTree, layouts: Mapping[CardId, CardLayout], card_id: CardId) -> float:
    """The product of the scales above ``card_id`` -- what a card inherits before its own factor."""
    total = 1.0
    for ancestor in tree.ancestors(card_id):
        state = layouts.get(ancestor)
        if state is not None:
            total *= state.scale
    return total


def _has_own_body(card: Card, blocks: Mapping[int, Block]) -> bool:
    """Whether a card's own blocks render into its body (a heading lives in the header)."""
    return any(
        block.kind is not BlockKind.HEADING
        for index in card.own_block_indexes
        if (block := blocks.get(index)) is not None
    )


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

    def place(
        self,
        card_id: CardId,
        *,
        x: float,
        y: float,
        width: float,
        depth: int,
        parent_scale: float = 1.0,
    ) -> float:
        """Place ``card_id`` and its subtree, returning the card's height."""
        card = self._tree.cards[card_id]
        state = self.state_of(card_id)
        own_scale = state.scale if state is not None else 1.0
        # Every metric scales with the *effective* factor (T-064/D-060): the card's own factor
        # times
        # its ancestors': a child inside a scaled card must grow with it, or its content clips.
        effective = parent_scale * own_scale
        box_width = width * own_scale
        inner_width = max(box_width - 2 * self._options.padding, _MIN_INNER_WIDTH)
        header = self._options.header_height * effective
        body = (
            self._estimator.estimate_height(card, blocks=self._blocks, width=inner_width)
            * effective
        )
        if card.child_ids and not _has_own_body(card, self._blocks):
            # A heading with nothing but child cards under it needs no empty body line: the children
            # follow the header bar directly, which tightens every such level (T-058).
            body = 0.0
        own_height = header + body + (2 * self._options.padding if body > 0.0 else 0.0)
        placeable = self.children_to_place(card)
        children_height = self._place_children(
            placeable,
            x=x + self._options.indent,
            y=y + own_height + self._options.gap,
            width=max(box_width - 2 * self._options.indent, _MIN_INNER_WIDTH),
            depth=depth,
            parent_scale=effective,
        )
        if body <= 0.0 and not placeable:
            # No body of its own and every child dragged out: the card is its title bar (T-059).
            height = own_height
        else:
            height = max(own_height + children_height, self._options.min_height)
        previous = self.state_of(card_id)
        layout = CardLayout(
            card_id=card_id,
            x=x,
            y=y,
            width=box_width,
            height=height,
            z=depth,
            collapsed=previous.collapsed if previous else False,
            detached=previous.detached if previous else False,
            manual_size=previous.manual_size if previous else False,
            scale=previous.scale if previous else 1.0,
            effective_scale=effective,
        )
        self.layouts[card_id] = layout
        return height

    def _place_children(
        self,
        child_ids: tuple[CardId, ...],
        *,
        x: float,
        y: float,
        width: float,
        depth: int,
        parent_scale: float = 1.0,
    ) -> float:
        total = 0.0
        for index, child_id in enumerate(child_ids):
            child_height = self.place(
                child_id,
                x=x,
                y=y + total,
                width=width,
                depth=depth + 1,
                parent_scale=parent_scale,
            )
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
    states: Mapping[CardId, CardLayout] | None = None,
) -> dict[CardId, CardLayout]:
    """Return a fresh attached layout for every card in ``tree``, in document order."""
    resolved = options or LinearLayoutOptions()
    placer = _Placer(tree, blocks, estimator, resolved, states=states)
    cursor = 0.0
    for root_id in tree.root_ids:
        height = placer.place(root_id, x=0.0, y=cursor, width=resolved.section_width, depth=0)
        cursor += height + resolved.gap
    # A free card is not part of anybody's flow, so the walk above skipped it. Place it as the tree
    # it is, at the position the user left it in (T-057 adds the scale, which must not be applied
    # twice: the stored width already carries it).
    for card_id, state in (states or {}).items():
        if card_id in tree.cards and card_id not in placer.layouts and state.detached:
            placer.place(
                card_id,
                x=state.x,
                y=state.y,
                width=state.width / (state.scale or 1.0),
                depth=state.z,
            )
    return placer.layouts


def relayout_subtree(
    tree: CardTree,
    layouts: Mapping[CardId, CardLayout],
    card_id: CardId,
    *,
    blocks: Mapping[int, Block],
    estimator: SizeEstimator,
    options: LinearLayoutOptions | None = None,
    base_width: float | None = None,
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
    # A stored width is what the card renders at, so the factor comes out again before the placer
    # applies it -- unless the caller already knows the unscaled width (T-057).
    width = base_width if base_width is not None else base.width / (base.scale or 1.0)
    placer.place(
        card_id,
        x=base.x,
        y=base.y,
        width=width,
        depth=base.z,
        parent_scale=_ancestor_scale(tree, layouts, card_id),
    )
    merged = dict(layouts)
    merged.update(placer.layouts)
    return merged
