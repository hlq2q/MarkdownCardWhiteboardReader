"""Unit tests for the tight-column helpers (T-036).

Shape under test, taken from the report: ``S > [G, H]``, ``G > P``, ``P > [A, B]``.
Every card's own content is one 40 px row, so a leaf is 98 px tall (34 header + 40 + 2 * 12)
and the numbers below stay checkable by hand.
"""

from __future__ import annotations

from collections.abc import Mapping

from mcwr.application.features.layout_board.service import (
    layout_board,
    relayout_subtree,
)
from mcwr.application.features.layout_board.stack import (
    hug_all,
    hug_children,
    propagate_height,
    resolve_overlaps,
    shift_subtree,
)
from mcwr.domain.enums import CardKind
from mcwr.domain.models import Block, Card, CardLayout, CardTree

GAP = 8.0
ROW = 86.0
PARENT_HEIGHT = 222.0  # 34 header only + 8 gap + 86 + 8 gap + 86
GRANDPARENT_HEIGHT = 264.0  # 34 header only + 8 gap + P


class FixedEstimator:
    """Content height stand-in (font metrics are not what these tests are about)."""

    def estimate_height(self, card: Card, *, blocks: Mapping[int, Block], width: float) -> float:
        del card, blocks, width
        return 40.0


def _card(
    card_id: str,
    parent: str | None,
    children: tuple[str, ...] = (),
    *,
    kind: CardKind = CardKind.HEADING,
    ordinal: int = 0,
) -> Card:
    return Card(
        card_id=card_id,
        kind=kind,
        parent_id=parent,
        child_ids=children,
        own_block_indexes=(),
        heading_path=(card_id,),
        ordinal_in_parent=ordinal,
        occurrence=0,
        content_hash=f"hash-{card_id}",
        title=card_id,
        level=1,
    )


def board() -> tuple[CardTree, dict[str, CardLayout]]:
    cards = {
        "S": _card("S", None, ("G", "H"), kind=CardKind.BIG_SECTION),
        "G": _card("G", "S", ("P",)),
        "H": _card("H", "S", (), ordinal=1),
        "P": _card("P", "G", ("A", "B")),
        "A": _card("A", "P"),
        "B": _card("B", "P", ordinal=1),
    }
    tree = CardTree(cards=cards, root_ids=("S",))
    return tree, layout_board(tree, blocks={}, estimator=FixedEstimator())


def _face(layouts: Mapping[str, CardLayout]) -> dict[str, tuple[float, float]]:
    return {card_id: (layout.y, layout.height) for card_id, layout in layouts.items()}


def test_the_fixture_matches_the_reported_shape() -> None:
    _, layouts = board()
    assert layouts["A"].height == ROW
    assert layouts["P"].height == PARENT_HEIGHT
    assert layouts["G"].height == GRANDPARENT_HEIGHT
    assert layouts["B"].y == layouts["A"].y + ROW + GAP
    assert layouts["H"].y == layouts["G"].y + GRANDPARENT_HEIGHT + GAP


def test_propagate_height_carries_the_change_up_the_chain() -> None:
    """Detaching A shrinks P; G, S and every card after them must follow (T-036)."""
    tree, layouts = board()
    before = _face(layouts)
    layouts["A"].detached = True
    packed = relayout_subtree(tree, layouts, "P", blocks={}, estimator=FixedEstimator())
    delta = packed["P"].height - before["P"][1]
    assert delta == -(ROW + GAP)
    propagate_height(tree, packed, "P", delta)
    assert packed["P"].height == PARENT_HEIGHT - ROW - GAP
    assert packed["G"].height == GRANDPARENT_HEIGHT - (ROW + GAP)
    assert packed["S"].height == before["S"][1] - (ROW + GAP)
    assert packed["H"].y == before["H"][0] - (ROW + GAP)
    assert packed["B"].y == before["A"][0]  # B still takes A's slot (reflow kept)


def test_detached_cards_and_their_subtrees_are_not_shifted() -> None:
    tree, layouts = board()
    before = _face(layouts)
    layouts["B"].detached = True
    shift_subtree(tree, layouts, "P", 100.0)
    assert layouts["P"].y == before["P"][0] + 100.0
    assert layouts["A"].y == before["A"][0] + 100.0
    assert layouts["B"].y == before["B"][0]


def test_resolve_overlaps_leaves_a_clear_column_alone() -> None:
    tree, layouts = board()
    layouts["B"].y = layouts["A"].y + ROW + 40.0  # clear, just further apart
    before = _face(layouts)
    assert resolve_overlaps(tree, layouts, all_parents=True) is False
    assert _face(layouts) == before


def test_the_dropped_card_wins_the_tie_and_the_other_moves_down() -> None:
    """B dropped on A's head must end up above A (the user's rule)."""
    tree, layouts = board()
    top = layouts["A"].y
    layouts["B"].y = top
    assert resolve_overlaps(tree, layouts, parent="P", dropped="B") is True
    assert layouts["B"].y == top
    assert layouts["A"].y == top + ROW + GAP


def test_the_same_rule_mirrors_when_a_is_the_one_dropped() -> None:
    tree, layouts = board()
    top = layouts["B"].y
    layouts["A"].y = top
    assert resolve_overlaps(tree, layouts, parent="P", dropped="A") is True
    assert layouts["A"].y == top
    assert layouts["B"].y == top + ROW + GAP


def test_a_card_dropped_back_into_its_own_slot_does_not_grow_the_boxes() -> None:
    """B lands where A was and A takes B's old slot: nothing sticks out, nothing grows."""
    tree, layouts = board()
    before = _face(layouts)
    layouts["B"].y = layouts["A"].y
    assert resolve_overlaps(tree, layouts, parent="P", dropped="B") is True
    assert layouts["P"].height == before["P"][1]
    assert layouts["G"].height == before["G"][1]
    assert layouts["S"].height == before["S"][1]
    assert layouts["H"].y == before["H"][0]


def test_a_stack_that_sticks_out_grows_the_boxes_and_pushes_the_cards_below() -> None:
    """A dropped on B's head: A stays on top, B now ends below where the box used to."""
    tree, layouts = board()
    before = _face(layouts)
    layouts["A"].y = layouts["B"].y
    assert resolve_overlaps(tree, layouts, parent="P", dropped="A") is True
    grown = ROW + GAP  # one row plus the sibling gap
    assert layouts["P"].height == before["P"][1] + grown
    assert layouts["G"].height == before["G"][1] + grown
    assert layouts["S"].height == before["S"][1] + grown
    assert layouts["H"].y == before["H"][0] + grown


def test_free_cards_may_sit_on_each_other() -> None:
    """The rule is about the flow inside a parent, not about free cards (FR-4.2)."""
    tree, layouts = board()
    layouts["A"].detached = True
    layouts["B"].detached = True
    layouts["B"].y = layouts["A"].y
    assert resolve_overlaps(tree, layouts, parent="P", dropped="B") is False
    assert layouts["B"].y == layouts["A"].y


def test_a_folded_parent_keeps_its_hidden_children_where_they_are() -> None:
    tree, layouts = board()
    layouts["P"].collapsed = True
    layouts["B"].y = layouts["A"].y
    assert resolve_overlaps(tree, layouts, parent="P", dropped="B") is False


def test_a_folded_box_does_not_follow_its_hidden_children() -> None:
    tree, layouts = board()
    layouts["G"].collapsed = True
    before = _face(layouts)
    propagate_height(tree, layouts, "P", -(ROW + GAP))
    assert layouts["G"].height == before["G"][1]
    assert layouts["H"].y == before["H"][0]


def test_hugging_pulls_the_bottom_edge_onto_the_lowest_child() -> None:
    tree, layouts = board()
    before = _face(layouts)
    layouts["B"].y -= 8.0  # lifted, still clear of A
    assert hug_children(tree, layouts, "P") is True
    assert layouts["P"].y + layouts["P"].height == layouts["B"].y + layouts["B"].height
    assert layouts["P"].height == before["P"][1] - 8.0
    assert layouts["G"].height == before["G"][1] - 8.0
    assert layouts["H"].y == before["H"][0] - 8.0


def test_hugging_grows_the_box_when_a_child_is_pushed_down() -> None:
    tree, layouts = board()
    before = _face(layouts)
    layouts["B"].y += 20.0
    assert hug_children(tree, layouts, "P") is True
    assert layouts["P"].height == before["P"][1] + 20.0
    assert layouts["G"].height == before["G"][1] + 20.0
    assert layouts["H"].y == before["H"][0] + 20.0


def test_hugging_a_box_that_already_touches_changes_nothing() -> None:
    tree, layouts = board()
    before = _face(layouts)
    assert hug_children(tree, layouts, "P") is False
    assert _face(layouts) == before


def test_hugging_leaves_a_folded_parent_and_a_childless_card_alone() -> None:
    tree, layouts = board()
    layouts["P"].collapsed = True
    before = _face(layouts)
    assert hug_children(tree, layouts, "P") is False
    assert _face(layouts) == before
    assert hug_children(tree, layouts, "H") is False  # H has no children


def test_hug_all_tightens_every_parent_at_once() -> None:
    tree, layouts = board()
    layouts["P"].height += 40.0  # a hand-made gap anywhere in the column
    assert hug_all(tree, layouts) is True
    assert layouts["P"].y + layouts["P"].height == layouts["B"].y + layouts["B"].height
    assert layouts["G"].y + layouts["G"].height == layouts["P"].y + layouts["P"].height
