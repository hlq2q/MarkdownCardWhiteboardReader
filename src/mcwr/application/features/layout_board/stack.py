"""Keep the column tight and free of overlaps (T-036).

:mod:`mcwr.application.features.layout_board.service` wraps a card's box around its own
content plus its children, and re-packs a single subtree in place. Two follow-ups live here:

* :func:`propagate_height` — when a subtree changes height, every ancestor box has to follow
  it and everything stacked below has to move by the same amount. Without it a shrunken
  parent left a hole inside its own parent (measured 114 px for one card) and the cards
  after it stayed where they were.
* :func:`resolve_overlaps` — two cards in the same parent must never sit on top of each
  other, and nothing prevented it: dragging only clamps an attached child to its parent's
  rectangle, so siblings could be dropped onto one another. The overlapping ones are ordered
  by their current top edge (whichever card was dropped on top stays on top) and pushed down
  just enough to clear, leaving cards that were already clear exactly where they are.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping

from mcwr.application.features.layout_board.service import LinearLayoutOptions
from mcwr.domain.models import CardId, CardLayout, CardTree


def _is_detached(layouts: Mapping[CardId, CardLayout], card_id: CardId) -> bool:
    layout = layouts.get(card_id)
    return bool(layout is not None and layout.detached)


def _is_collapsed(layouts: Mapping[CardId, CardLayout], card_id: CardId) -> bool:
    layout = layouts.get(card_id)
    return bool(layout is not None and layout.collapsed)


def move_subtree(
    tree: CardTree,
    layouts: MutableMapping[CardId, CardLayout],
    card_id: CardId,
    dx: float,
    dy: float,
) -> None:
    """Move ``card_id`` and its attached descendants by (``dx``, ``dy``).

    A free card is part of no flow, so a detached card and its subtree stay where the user left
    them (FR-4.2). Used both to carry a height change down the column (``dx`` = 0) and to keep a
    moved card's subtree travelling with it (T-043, D-050).
    """
    if dx == 0.0 and dy == 0.0:
        return
    pending = [card_id]
    while pending:
        current = pending.pop()
        if _is_detached(layouts, current):
            continue
        layout = layouts.get(current)
        if layout is not None:
            layout.x += dx
            layout.y += dy
        pending.extend(tree.cards[current].child_ids)


def shift_subtree(
    tree: CardTree,
    layouts: MutableMapping[CardId, CardLayout],
    card_id: CardId,
    delta: float,
) -> None:
    """Move ``card_id`` and its attached descendants down by ``delta`` (y only)."""
    move_subtree(tree, layouts, card_id, 0.0, delta)


def _siblings(
    tree: CardTree, layouts: Mapping[CardId, CardLayout], parent: CardId | None
) -> tuple[CardId, ...]:
    """The cards that take part in the flow of ``parent`` (``None`` = the top level)."""
    ids = tree.root_ids if parent is None else tree.cards[parent].child_ids
    return tuple(card_id for card_id in ids if not _is_detached(layouts, card_id))


def _shift_tail(
    tree: CardTree,
    layouts: MutableMapping[CardId, CardLayout],
    parent: CardId | None,
    after: CardId,
    delta: float,
) -> None:
    """Move everything stacked after ``after`` inside ``parent`` (``None`` = top level)."""
    ids = tree.root_ids if parent is None else tree.cards[parent].child_ids
    following = False
    for card_id in ids:
        if following:
            shift_subtree(tree, layouts, card_id, delta)
        elif card_id == after:
            following = True


def propagate_height(
    tree: CardTree,
    layouts: MutableMapping[CardId, CardLayout],
    card_id: CardId,
    delta: float,
) -> None:
    """Carry ``card_id``'s height change up the chain (T-036).

    ``card_id``'s own box already changed by ``delta``. Each ancestor box follows by the same
    amount, and the cards stacked after it move by it too, so no hole is left behind and the
    arrangement below keeps its relative shape (the user's rule: "不留下空缺,使布局紧凑").
    A folded ancestor hides its children, so its box does not depend on them and the chain
    stops there.
    """
    if delta == 0.0:
        return
    changed = card_id
    for ancestor in tree.ancestors(card_id):
        _shift_tail(tree, layouts, ancestor, changed, delta)
        box = layouts.get(ancestor)
        if box is None or box.collapsed:
            return
        box.height = max(box.height + delta, 0.0)
        changed = ancestor
    _shift_tail(tree, layouts, None, changed, delta)


def _push_overlaps(
    tree: CardTree,
    layouts: MutableMapping[CardId, CardLayout],
    children: tuple[CardId, ...],
    gap: float,
) -> tuple[bool, float]:
    """Push each child that sits on the previous one down; returns ``(moved, bottom)``.

    Order is by the current top edge (a tie keeps the order of ``children``, which is document
    order). ``bottom`` is where the stack ends after the sweep, which is what the parent's box
    has to cover — not how much it moved, because a card may already sit in the space it needs.
    """
    ordered = sorted(children, key=lambda card_id: layouts[card_id].y)
    bottom = layouts[ordered[0]].y + layouts[ordered[0]].height
    moved = False
    for card_id in ordered[1:]:
        layout = layouts[card_id]
        if layout.y < bottom:
            shift_subtree(tree, layouts, card_id, bottom + gap - layout.y)
            moved = True
        bottom = layout.y + layout.height
    return moved, bottom


def resolve_overlaps(
    tree: CardTree,
    layouts: MutableMapping[CardId, CardLayout],
    *,
    parent: CardId | None = None,
    all_parents: bool = False,
    options: LinearLayoutOptions | None = None,
) -> bool:
    """Separate cards that overlap inside the same parent; True when something moved.

    ``parent`` limits the sweep to one card's children; ``all_parents`` sweeps the whole board
    (after a structural operation, which is where the user wants the invariant restored). Free
    cards and folded parents are skipped: neither has a flow to keep tidy.

    A box only ever grows here, and only by the amount the stack now sticks out of it: a card
    dropped back into the space it came from leaves the stack exactly as tall as it was, and
    growing the ancestors for that would leave a hole under the last child (seen in
    ``spikes/_out/stack_after_drop_t036.png`` before this rule existed).
    """
    resolved = options or LinearLayoutOptions()
    targets: tuple[CardId | None, ...] = (None, *tree.ordered_ids()) if all_parents else (parent,)
    moved = False
    for target in targets:
        if target is not None and _is_collapsed(layouts, target):
            continue
        children = _siblings(tree, layouts, target)
        if len(children) < 2:
            continue
        pushed, bottom = _push_overlaps(tree, layouts, children, resolved.gap)
        if not pushed:
            continue
        moved = True
        if target is None:
            continue
        box = layouts.get(target)
        if box is None:
            continue
        needed = bottom - (box.y + box.height)
        if needed > 0.0:
            box.height += needed
            propagate_height(tree, layouts, target, needed)
    return moved


def hug_children(
    tree: CardTree, layouts: MutableMapping[CardId, CardLayout], parent: CardId
) -> bool:
    """End the box where its lowest attached child ends (T-041); True when it moved.

    The rule the user asked for while arranging cards inside a parent: the parent's bottom edge
    always coincides with the lowest child's bottom edge, so lifting a child closes the gap up
    and the box grows again when one is pushed down -- both carried up the ancestor chain.
    A folded parent keeps its small box (its children are hidden) and a parent with no attached
    child is left alone; free cards are part of no flow, so they cannot hug anything.
    """
    box = layouts.get(parent)
    if box is None or box.collapsed:
        return False
    children = _siblings(tree, layouts, parent)
    if not children:
        return False
    bottom = max(layouts[card_id].y + layouts[card_id].height for card_id in children)
    needed = bottom - (box.y + box.height)
    if needed == 0.0:
        return False
    box.height = max(box.height + needed, 0.0)
    propagate_height(tree, layouts, parent, needed)
    return True


def hug_all(tree: CardTree, layouts: MutableMapping[CardId, CardLayout]) -> bool:
    """Apply :func:`hug_children` to every parent; True when anything moved (T-041).

    Used after a structural operation and when a document is opened or refreshed, so a stored
    arrangement that carries a gap heals as soon as it is loaded.
    """
    moved = False
    for card_id in tree.ordered_ids():
        if hug_children(tree, layouts, card_id):
            moved = True
    return moved
