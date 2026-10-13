"""Tests for the initial linear layout (FR-3.1, invariant 3)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import astuple

import pytest

from mcwr.application.features.build_card_tree.service import build_card_tree
from mcwr.application.features.layout_board.service import (
    LinearLayoutOptions,
    layout_board,
    relayout_subtree,
)
from mcwr.domain.enums import BlockKind
from mcwr.domain.ids import normalize_text
from mcwr.domain.models import Block, Card, CardLayout, CardTree

PATH_HASH = "0123456789ab"


class FixedEstimator:
    """Deterministic stand-in for font metrics."""

    def __init__(self, height: float = 40.0) -> None:
        self.height = height
        self.calls: list[tuple[str, float]] = []

    def estimate_height(self, card: Card, *, blocks: Mapping[int, Block], width: float) -> float:
        self.calls.append((card.card_id, width))
        return self.height


def blk(index: int, kind: BlockKind, text: str, *, level: int | None = None) -> Block:
    return Block(
        index=index,
        kind=kind,
        raw_text=text,
        text_normalized=normalize_text(text),
        level=level,
    )


def sample_tree() -> CardTree:
    blocks = [
        blk(0, BlockKind.HEADING, "Intro", level=1),
        blk(1, BlockKind.PARAGRAPH, "some text"),
        blk(2, BlockKind.HEADING, "Deep", level=2),
        blk(
            3,
            BlockKind.CODE,
            "print(1)",
        ),
        blk(4, BlockKind.THEMATIC_BREAK, "---"),
        blk(5, BlockKind.HEADING, "Second", level=1),
    ]
    return build_card_tree(blocks, path_hash=PATH_HASH)


def layout(tree: CardTree, *, height: float = 40.0) -> dict[str, CardLayout]:
    blocks = {index: blk(index, BlockKind.PARAGRAPH, "x") for index in range(6)}
    return layout_board(tree, blocks=blocks, estimator=FixedEstimator(height))


def test_every_card_is_placed_exactly_once() -> None:
    tree = sample_tree()
    result = layout(tree)
    assert set(result) == set(tree.cards)


def test_children_sit_inside_their_parent() -> None:
    tree = sample_tree()
    result = layout(tree)
    for card in tree.cards.values():
        parent = result.get(card.parent_id or "")
        if parent is None:
            continue
        child = result[card.card_id]
        assert child.x >= parent.x
        assert child.y >= parent.y
        assert child.x + child.width <= parent.x + parent.width
        assert child.y + child.height <= parent.y + parent.height


def test_roots_stack_without_overlap_and_in_order() -> None:
    tree = sample_tree()
    result = layout(tree)
    assert len(tree.root_ids) == 2
    first, second = (result[root] for root in tree.root_ids)
    assert first.y < second.y
    assert second.y >= first.y + first.height


def test_reading_order_is_top_to_bottom() -> None:
    tree = sample_tree()
    result = layout(tree)
    ys = [result[card_id].y for card_id in tree.ordered_ids()]
    assert ys == sorted(ys)


def test_depth_drives_z_order() -> None:
    tree = sample_tree()
    result = layout(tree)
    for card_id in tree.ordered_ids():
        depth = len(tree.ancestors(card_id))
        assert result[card_id].z == depth


def test_layout_is_deterministic() -> None:
    tree = sample_tree()
    first = layout(tree)
    second = layout(tree)
    assert {key: astuple(value) for key, value in first.items()} == {
        key: astuple(value) for key, value in second.items()
    }


def test_parent_grows_to_hold_its_children() -> None:
    tree = sample_tree()
    result = layout(tree, height=100.0)
    for root_id in tree.root_ids:
        root = result[root_id]
        descendants = [result[card] for card in tree.descendants(root_id)]
        assert descendants, "the sample has nested cards"
        for child in descendants:
            assert child.y + child.height <= root.y + root.height


def test_options_control_the_root_width() -> None:
    tree = sample_tree()
    blocks = {index: blk(index, BlockKind.PARAGRAPH, "x") for index in range(6)}
    options = LinearLayoutOptions(section_width=500.0, gap=5.0)
    result = layout_board(tree, blocks=blocks, estimator=FixedEstimator(), options=options)
    assert result[tree.root_ids[0]].width == 500.0


def test_detached_cards_are_not_placed_here() -> None:
    """layout_board always produces the attached arrangement (FR-4.6: 'restore all')."""
    tree = sample_tree()
    result = layout(tree)
    assert all(layout.detached is False for layout in result.values())
    assert all(layout.collapsed is False for layout in result.values())


def _states() -> dict[str, CardLayout]:
    tree = sample_tree()
    return layout(tree, height=60.0)


def test_relayout_subtree_keeps_other_cards_untouched() -> None:
    tree = sample_tree()
    layouts = _states()
    second_root = tree.root_ids[1]
    before = astuple(layouts[second_root])

    updated = relayout_subtree(
        tree,
        layouts,
        tree.root_ids[0],
        blocks={},
        estimator=FixedEstimator(),
    )

    assert astuple(updated[second_root]) == before


def test_collapsed_parent_shrinks_and_remembers_child_geometry() -> None:
    tree = sample_tree()
    layouts = _states()
    section = tree.root_ids[0]
    child = tree.cards[section].child_ids[0]
    tall = layouts[section].height
    child_box = astuple(layouts[child])
    layouts[section].collapsed = True

    updated = relayout_subtree(tree, layouts, section, blocks={}, estimator=FixedEstimator())

    assert updated[section].height < tall
    assert astuple(updated[child]) == child_box, "hidden cards keep their remembered geometry"
    assert updated[section].collapsed is True


def test_detached_child_is_not_pulled_back_inside_its_parent() -> None:
    tree = sample_tree()
    layouts = _states()
    section = tree.root_ids[0]
    child = tree.cards[section].child_ids[0]
    layouts[child].detached = True
    layouts[child].x = 5000.0
    layouts[child].y = 5000.0

    updated = relayout_subtree(tree, layouts, section, blocks={}, estimator=FixedEstimator())

    assert (updated[child].x, updated[child].y) == (5000.0, 5000.0)
    assert updated[child].detached is True


def test_relayout_subtree_requires_an_existing_layout() -> None:
    tree = sample_tree()
    with pytest.raises(KeyError):
        relayout_subtree(tree, {}, tree.root_ids[0], blocks={}, estimator=FixedEstimator())
