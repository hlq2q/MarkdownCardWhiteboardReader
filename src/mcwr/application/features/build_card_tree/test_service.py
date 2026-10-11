"""Tests for card-tree construction (spec §2.3, FR-2)."""

from __future__ import annotations

from collections.abc import Mapping

from mcwr.application.features.build_card_tree.service import build_card_tree
from mcwr.domain.enums import BlockKind, CardKind
from mcwr.domain.ids import normalize_text
from mcwr.domain.invariants import required_block_indexes, tree_problems
from mcwr.domain.models import Block, Card, CardTree

PATH_HASH = "deadbeef0000"


def blk(
    index: int,
    kind: BlockKind,
    text: str,
    *,
    level: int | None = None,
    lang: str | None = None,
    attrs: Mapping[str, str] | None = None,
) -> Block:
    return Block(
        index=index,
        kind=kind,
        raw_text=text,
        text_normalized=normalize_text(text),
        level=level,
        lang=lang,
        attrs=dict(attrs or {}),
    )


def heading(index: int, text: str, level: int) -> Block:
    return blk(index, BlockKind.HEADING, text, level=level)


def para(index: int, text: str) -> Block:
    return blk(index, BlockKind.PARAGRAPH, text)


def divider(index: int) -> Block:
    return blk(index, BlockKind.THEMATIC_BREAK, "---")


def build(blocks: list[Block]) -> CardTree:
    return build_card_tree(blocks, path_hash=PATH_HASH)


def titled(tree: CardTree, title: str) -> Card:
    matches = [card for card in tree.cards.values() if card.title == title]
    assert len(matches) == 1, f"expected exactly one card titled {title!r}, got {len(matches)}"
    return matches[0]


def test_document_without_dividers_is_a_single_big_section() -> None:
    tree = build([heading(0, "Intro", 1), para(1, "hello")])
    assert len(tree.root_ids) == 1
    root = tree.cards[tree.root_ids[0]]
    assert root.kind is CardKind.BIG_SECTION
    assert root.title == "Section 1"
    assert root.own_block_indexes == ()


def test_dividers_split_the_document_into_big_sections() -> None:
    blocks = [heading(0, "A", 1), divider(1), heading(2, "B", 1), divider(3), heading(4, "C", 1)]
    tree = build(blocks)
    assert [tree.cards[root].kind for root in tree.root_ids] == [CardKind.BIG_SECTION] * 3
    assert [tree.cards[root].title for root in tree.root_ids] == [
        "Section 1",
        "Section 2",
        "Section 3",
    ]


def test_consecutive_and_edge_dividers_never_create_empty_sections() -> None:
    blocks = [divider(0), para(1, "a"), divider(2), divider(3), para(4, "b"), divider(5)]
    tree = build(blocks)
    assert len(tree.root_ids) == 2
    for root in tree.root_ids:
        assert tree.cards[root].own_block_indexes, "empty big sections must not exist"


def test_headings_nest_by_level() -> None:
    blocks = [
        heading(0, "A", 1),
        heading(1, "B", 2),
        heading(2, "C", 3),
        heading(3, "D", 2),
    ]
    tree = build(blocks)
    section = tree.cards[tree.root_ids[0]]
    a = titled(tree, "A")
    b = titled(tree, "B")
    c = titled(tree, "C")
    d = titled(tree, "D")
    assert section.child_ids == (a.card_id,)
    assert a.child_ids == (b.card_id, d.card_id)
    assert b.child_ids == (c.card_id,)
    assert c.child_ids == ()


def test_level_jump_attaches_to_the_nearest_lower_heading() -> None:
    tree = build([heading(0, "A", 1), heading(1, "C", 3)])
    a = titled(tree, "A")
    c = titled(tree, "C")
    assert c.parent_id == a.card_id
    assert c.heading_path == ("A", "C")


def test_content_blocks_belong_to_the_nearest_heading() -> None:
    blocks = [
        heading(0, "A", 1),
        para(1, "before"),
        heading(2, "B", 2),
        para(3, "after"),
    ]
    tree = build(blocks)
    assert titled(tree, "A").own_block_indexes == (0, 1)
    assert titled(tree, "B").own_block_indexes == (2, 3)


def test_card_blocks_without_a_heading_belong_to_the_big_section() -> None:
    blocks = [para(0, "lead in"), blk(1, BlockKind.CODE, "print(1)", lang="python")]
    tree = build(blocks)
    section = tree.cards[tree.root_ids[0]]
    assert section.own_block_indexes == (0,)
    code = titled(tree, "python")
    assert code.parent_id == section.card_id
    assert code.kind is CardKind.CODE
    assert code.own_block_indexes == (1,)


def test_every_block_is_owned_exactly_once() -> None:
    blocks = [
        para(0, "lead"),
        heading(1, "A", 1),
        para(2, "text"),
        blk(3, BlockKind.TABLE, "| a |"),
        heading(4, "B", 2),
        blk(5, BlockKind.MATH_BLOCK, "$$x$$"),
        divider(6),
        blk(7, BlockKind.MERMAID, "graph TD;", lang="mermaid"),
        blk(8, BlockKind.TASK_LIST, "- [ ] todo"),
    ]
    tree = build(blocks)
    assert tree_problems(tree, required_indexes=required_block_indexes(blocks)) == ()


def test_repeated_sibling_titles_get_distinct_identities() -> None:
    tree = build([heading(0, "Notes", 2), para(1, "a"), heading(2, "Notes", 2)])
    notes = [card for card in tree.cards.values() if card.title == "Notes"]
    assert len(notes) == 2
    assert notes[0].card_id != notes[1].card_id
    assert [card.occurrence for card in notes] == [0, 1]


def test_repeated_code_blocks_get_distinct_identities() -> None:
    blocks = [
        heading(0, "A", 1),
        blk(1, BlockKind.CODE, "x = 1", lang="python"),
        blk(2, BlockKind.CODE, "x = 2", lang="python"),
    ]
    tree = build(blocks)
    codes = [card for card in tree.cards.values() if card.kind is CardKind.CODE]
    assert len({card.card_id for card in codes}) == 2
    assert sorted(card.ordinal_in_parent for card in codes) == [0, 1]


def test_content_edits_keep_the_card_identity_but_change_the_hash() -> None:
    before = build([heading(0, "A", 1), para(1, "first wording")])
    after = build([heading(0, "A", 1), para(1, "second wording")])
    assert titled(before, "A").card_id == titled(after, "A").card_id
    assert titled(before, "A").content_hash != titled(after, "A").content_hash


def test_heading_paths_track_the_ancestry() -> None:
    tree = build([heading(0, "A", 1), heading(1, "B", 2), blk(2, BlockKind.TABLE, "| x |")])
    table = titled(tree, "table")
    assert table.heading_path == ("A", "B")


def test_empty_document_yields_an_empty_tree() -> None:
    tree = build([])
    assert tree.cards == {}
    assert tree.root_ids == ()


def test_document_of_only_dividers_yields_an_empty_tree() -> None:
    tree = build([divider(0), divider(1)])
    assert tree.cards == {}


def test_same_document_hashes_survive_rebuild_from_scratch() -> None:
    blocks = [heading(0, "A", 1), para(1, "text")]
    assert build(blocks).ordered_ids() == build(blocks).ordered_ids()
