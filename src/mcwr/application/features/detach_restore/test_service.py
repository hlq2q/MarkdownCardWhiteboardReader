"""Tests for the detach / restore / fold state machine (FR-4, FR-3.7)."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from mcwr.application.features.build_card_tree.service import build_card_tree
from mcwr.application.features.detach_restore.service import (
    can_detach,
    detach_card,
    reclaim_children,
    restore_all,
    restore_card,
    toggle_collapse,
)
from mcwr.application.features.layout_board.service import layout_board
from mcwr.domain.enums import BlockKind
from mcwr.domain.ids import normalize_text
from mcwr.domain.models import Block, Card, CardLayout, CardTree


class FixedEstimator:
    def estimate_height(self, card: Card, *, blocks: Mapping[int, Block], width: float) -> float:
        return 40.0


def blk(
    index: int, kind: BlockKind, text: str, *, level: int | None = None, lang: str | None = None
) -> Block:
    return Block(
        index=index,
        kind=kind,
        raw_text=text,
        text_normalized=normalize_text(text),
        level=level,
        lang=lang,
    )


def fixture() -> tuple[CardTree, dict[str, CardLayout]]:
    blocks = [
        blk(0, BlockKind.HEADING, "Intro", level=1),
        blk(1, BlockKind.PARAGRAPH, "text"),
        blk(2, BlockKind.HEADING, "Deep", level=2),
        blk(3, BlockKind.CODE, "print(1)", lang="python"),
        blk(4, BlockKind.THEMATIC_BREAK, "---"),
        blk(5, BlockKind.HEADING, "Second", level=1),
    ]
    tree = build_card_tree(blocks, path_hash="aaaa00001111")
    layouts = layout_board(
        tree, blocks={block.index: block for block in blocks}, estimator=FixedEstimator()
    )
    return tree, layouts


def card_id_of(tree: CardTree, title: str) -> str:
    matches = [card.card_id for card in tree.cards.values() if card.title == title]
    assert len(matches) == 1, f"expected one card titled {title!r}"
    return matches[0]


def test_top_level_cards_cannot_be_detached() -> None:
    tree, layouts = fixture()
    section = tree.root_ids[0]
    assert can_detach(tree, section) is False
    change = detach_card(tree, layouts, section)
    assert change.changed is False
    assert change.blocked == (section,)
    assert "top-level" in change.reason
    assert layouts[section].detached is False


def test_nested_cards_can_be_detached_and_restored() -> None:
    tree, layouts = fixture()
    code = card_id_of(tree, "python")
    assert can_detach(tree, code) is True

    detached = detach_card(tree, layouts, code)
    assert detached.affected == (code,)
    assert detached.relayout is True
    assert layouts[code].detached is True
    assert tree.cards[code].parent_id is not None, "the logical parent link must survive"

    restored = restore_card(tree, layouts, code)
    assert restored.affected == (code,)
    assert layouts[code].detached is False


def test_operations_are_idempotent() -> None:
    tree, layouts = fixture()
    code = card_id_of(tree, "python")
    assert detach_card(tree, layouts, code).changed is True
    assert detach_card(tree, layouts, code).changed is False
    assert restore_card(tree, layouts, code).changed is True
    assert restore_card(tree, layouts, code).changed is False


def test_restoring_an_attached_card_is_blocked_with_a_reason() -> None:
    tree, layouts = fixture()
    code = card_id_of(tree, "python")
    change = restore_card(tree, layouts, code)
    assert change.changed is False
    assert change.blocked == (code,)
    assert "not a free card" in change.reason


def test_reclaim_children_only_touches_free_descendants() -> None:
    tree, layouts = fixture()
    intro = card_id_of(tree, "Intro")
    deep = card_id_of(tree, "Deep")
    code = card_id_of(tree, "python")
    detach_card(tree, layouts, deep)
    detach_card(tree, layouts, code)

    change = reclaim_children(tree, layouts, intro)

    assert set(change.affected) == {deep, code}
    assert layouts[deep].detached is False
    assert layouts[code].detached is False


def test_reclaim_children_of_a_leaf_is_a_noop() -> None:
    tree, layouts = fixture()
    code = card_id_of(tree, "python")
    assert reclaim_children(tree, layouts, code).changed is False


def test_restore_all_clears_detach_and_fold_everywhere() -> None:
    tree, layouts = fixture()
    deep = card_id_of(tree, "Deep")
    code = card_id_of(tree, "python")
    detach_card(tree, layouts, code)
    toggle_collapse(tree, layouts, deep)

    change = restore_all(tree, layouts)

    assert set(change.affected) == {code, deep}
    assert all(layout.detached is False for layout in layouts.values())
    assert all(layout.collapsed is False for layout in layouts.values())


def test_fold_flips_and_remembers_child_geometry() -> None:
    tree, layouts = fixture()
    intro = card_id_of(tree, "Intro")
    deep = card_id_of(tree, "Deep")
    before = (layouts[deep].x, layouts[deep].y, layouts[deep].width, layouts[deep].height)

    assert toggle_collapse(tree, layouts, intro).changed is True
    assert layouts[intro].collapsed is True
    assert (layouts[deep].x, layouts[deep].y, layouts[deep].width, layouts[deep].height) == before

    assert toggle_collapse(tree, layouts, intro).changed is True
    assert layouts[intro].collapsed is False


def test_folding_a_leaf_is_blocked() -> None:
    tree, layouts = fixture()
    code = card_id_of(tree, "python")
    change = toggle_collapse(tree, layouts, code)
    assert change.changed is False
    assert "no children" in change.reason


def test_unknown_card_is_a_programming_error() -> None:
    tree, layouts = fixture()
    with pytest.raises(KeyError):
        detach_card(tree, layouts, "no-such-card")
    with pytest.raises(KeyError):
        toggle_collapse(tree, layouts, "no-such-card")


def test_missing_layout_is_created_on_demand() -> None:
    tree, layouts = fixture()
    code = card_id_of(tree, "python")
    del layouts[code]
    change = detach_card(tree, layouts, code)
    assert change.affected == (code,)
    assert layouts[code].detached is True
