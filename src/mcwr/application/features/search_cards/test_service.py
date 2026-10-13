"""Tests for the search slice (T-019): case sensitivity, scope, order and counting.

Pure: blocks and a card tree in, hits out — no Qt, no filesystem.
"""

from __future__ import annotations

from mcwr.application.features.build_card_tree.service import build_card_tree
from mcwr.application.features.search_cards.models import SearchHit
from mcwr.application.features.search_cards.service import card_text, search_cards
from mcwr.domain.enums import BlockKind
from mcwr.domain.ids import normalize_text
from mcwr.domain.models import Block, CardTree

PATH_HASH = "deadbeef"


def heading(index: int, text: str, level: int = 1) -> Block:
    return Block(
        index=index,
        kind=BlockKind.HEADING,
        raw_text=f"{'#' * level} {text}",
        text_normalized=normalize_text(text),
        level=level,
    )


def paragraph(index: int, text: str) -> Block:
    return Block(
        index=index,
        kind=BlockKind.PARAGRAPH,
        raw_text=text,
        text_normalized=normalize_text(text),
    )


def code(index: int, text: str, lang: str = "python") -> Block:
    return Block(
        index=index,
        kind=BlockKind.CODE,
        raw_text=f"```{lang}\n{text}\n```",
        text_normalized=normalize_text(text),
        lang=lang,
    )


def build(*blocks: Block) -> tuple[CardTree, dict[int, Block]]:
    tree = build_card_tree(blocks, path_hash=PATH_HASH)
    return tree, {block.index: block for block in blocks}


def titles(hits: tuple[SearchHit, ...]) -> list[str]:
    return [hit.title for hit in hits]


def test_a_title_matches_its_own_card_once() -> None:
    """A heading's title is its heading text, so one visible occurrence is counted once."""
    tree, blocks = build(heading(0, "Beta"), paragraph(1, "text b"))
    hits = search_cards(tree, blocks, "Beta")
    assert titles(hits) == ["Beta"]
    assert hits[0].matches == 1


def test_the_match_is_case_sensitive() -> None:
    tree, blocks = build(heading(0, "Beta"), paragraph(1, "text b"))
    assert search_cards(tree, blocks, "beta") == ()
    assert titles(search_cards(tree, blocks, "Beta")) == ["Beta"]


def test_body_text_matches_even_when_the_title_does_not() -> None:
    tree, blocks = build(heading(0, "Alpha"), paragraph(1, "needle in the body"))
    hits = search_cards(tree, blocks, "needle")
    assert titles(hits) == ["Alpha"]


def test_a_parent_never_matches_its_children_s_text() -> None:
    """Card content is its own blocks (D-005): the hit belongs to the card that draws it."""
    tree, blocks = build(
        heading(0, "Top"),
        paragraph(1, "own text"),
        heading(2, "Child", level=2),
        paragraph(3, "hidden needle"),
    )
    hits = search_cards(tree, blocks, "hidden needle")
    assert titles(hits) == ["Child"]


def test_hits_come_back_in_document_order() -> None:
    tree, blocks = build(
        heading(0, "One"),
        paragraph(1, "shared"),
        heading(2, "Two"),
        paragraph(3, "shared"),
        heading(4, "Three"),
        paragraph(5, "shared"),
    )
    assert titles(search_cards(tree, blocks, "shared")) == ["One", "Two", "Three"]


def test_occurrences_are_counted_inside_one_card() -> None:
    tree, blocks = build(heading(0, "One"), paragraph(1, "tok tok tok"))
    hits = search_cards(tree, blocks, "tok")
    assert hits[0].matches == 3


def test_cjk_text_is_searchable() -> None:
    tree, blocks = build(heading(0, "章节"), paragraph(1, "这是正文，含中文关键词。"))
    assert titles(search_cards(tree, blocks, "中文关键词")) == ["章节"]


def test_a_code_card_can_be_found_by_its_language() -> None:
    tree, blocks = build(heading(0, "One"), code(1, "print(1)", lang="python"))
    assert titles(search_cards(tree, blocks, "python")) == ["python"]


def test_an_empty_query_finds_nothing() -> None:
    tree, blocks = build(heading(0, "One"), paragraph(1, "text"))
    assert search_cards(tree, blocks, "") == ()


def test_a_missing_query_returns_no_hits_rather_than_none() -> None:
    tree, blocks = build(heading(0, "One"), paragraph(1, "text"))
    assert search_cards(tree, blocks, "nothing here") == ()


def test_card_text_keeps_the_own_blocks_verbatim() -> None:
    tree, blocks = build(heading(0, "One"), paragraph(1, "body line"))
    card = next(card for card in tree.cards.values() if card.kind.value == "heading")
    text = card_text(card, blocks)
    assert "One" in text
    assert "body line" in text
