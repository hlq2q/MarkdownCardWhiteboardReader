"""Tests for the pure domain models."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from mcwr.domain.enums import BlockKind, BlockRole, CardKind, card_kind_for, role_of
from mcwr.domain.invariants import tree_problems
from mcwr.domain.models import Card, CardTree, SourceSpan, Viewport


def _card(card_id: str, *, parent: str | None, children: tuple[str, ...], blocks: tuple[int, ...],
          kind: CardKind = CardKind.HEADING, level: int | None = 1) -> Card:
    return Card(
        card_id=card_id,
        kind=kind,
        parent_id=parent,
        child_ids=children,
        own_block_indexes=blocks,
        heading_path=(card_id,),
        ordinal_in_parent=0,
        occurrence=0,
        content_hash="0" * 12,
        title=card_id,
        level=level,
    )


def _tree() -> CardTree:
    cards = {
        "root": _card(
            "root", parent=None, children=("h2",), blocks=(0,), kind=CardKind.HEADING, level=1
        ),
        "h2": _card("h2", parent="root", children=("code",), blocks=(1,), level=2),
        "code": _card(
            "code", parent="h2", children=(), blocks=(2,), kind=CardKind.CODE, level=None
        ),
    }
    return CardTree(cards=cards, root_ids=("root",))


def test_viewport_bounds_are_class_level_not_fields() -> None:
    names = {field.name for field in dataclasses.fields(Viewport)}
    assert names == {"scale", "pan_x", "pan_y", "fitted_once"}


def test_viewport_scale_is_clamped() -> None:
    viewport = Viewport()
    viewport.set_scale(99.0)
    assert viewport.scale == Viewport.MAX_SCALE
    viewport.set_scale(0.0)
    assert viewport.scale == Viewport.MIN_SCALE


def test_source_span_rejects_inverted_ranges() -> None:
    with pytest.raises(ValueError, match="invalid source span"):
        SourceSpan(start_line=5, end_line=4)


def test_card_layout_mutation_helpers() -> None:
    from mcwr.domain.models import CardLayout

    layout = CardLayout(card_id="c1")
    layout.move_to(10, 20)
    layout.resize_to(300, 200)
    assert (layout.x, layout.y, layout.width, layout.height) == (10, 20, 300, 200)
    assert layout.manual_size is True


def test_tree_navigation_helpers() -> None:
    tree = _tree()
    assert tree.ordered_ids() == ("root", "h2", "code")
    assert tree.ancestors("code") == ("h2", "root")
    assert tree.descendants("root") == ("h2", "code")
    assert tree.descendants("code") == ()


def test_invariants_accept_a_well_formed_tree() -> None:
    assert tree_problems(_tree(), required_indexes={0, 1, 2}) == ()


def test_invariants_report_missing_and_duplicate_coverage() -> None:
    tree = _tree()
    cards = dict(tree.cards)
    cards["h2"] = dataclasses.replace(cards["h2"], own_block_indexes=(0,))
    broken = CardTree(cards=cards, root_ids=tree.root_ids)
    problems = tree_problems(broken, required_indexes={0, 1, 2})
    assert any("owned by several cards" in problem for problem in problems)
    assert any("block coverage mismatch" in problem for problem in problems)


def test_invariants_report_unreachable_cards() -> None:
    tree = _tree()
    cards = dict(tree.cards)
    ghost = _card("ghost", parent=None, children=(), blocks=(), kind=CardKind.TABLE, level=None)
    cards["ghost"] = ghost
    broken = CardTree(cards=cards, root_ids=tree.root_ids)
    problems = tree_problems(broken, required_indexes={0, 1, 2})
    assert any("not reachable" in problem for problem in problems)


def test_block_roles_match_the_spec() -> None:
    for kind in (BlockKind.HEADING, BlockKind.TABLE, BlockKind.MATH_BLOCK, BlockKind.MERMAID,
                 BlockKind.TASK_LIST, BlockKind.TOC, BlockKind.IMAGE, BlockKind.CODE):
        assert role_of(kind) is BlockRole.CARD
    for kind in (BlockKind.PARAGRAPH, BlockKind.BLOCKQUOTE, BlockKind.LIST, BlockKind.HTML,
                 BlockKind.UNKNOWN):
        assert role_of(kind) is BlockRole.CONTENT
    assert role_of(BlockKind.THEMATIC_BREAK) is BlockRole.DIVIDER
    assert card_kind_for(BlockKind.PARAGRAPH) is None
    assert card_kind_for(BlockKind.MERMAID) is CardKind.MERMAID


def test_document_key_roundtrip_fields() -> None:
    from mcwr.domain.models import DocumentKey

    key = DocumentKey(path=Path("a.md"), path_hash="h", size=1, mtime=2.0, content_hash="c")
    assert key.path.name == "a.md"
