"""Tests for the heuristic size estimator."""

from __future__ import annotations

from collections.abc import Mapping

from mcwr.domain.enums import BlockKind, CardKind
from mcwr.domain.models import TOC_ENTRIES_ATTR, Block, Card
from mcwr.infrastructure.heuristic_sizer import HeuristicSizeEstimator


def block(index: int, text: str) -> Block:
    return Block(index=index, kind=BlockKind.PARAGRAPH, raw_text=text, text_normalized=text)


def card(kind: CardKind, blocks: tuple[int, ...]) -> Card:
    return Card(
        card_id="c",
        kind=kind,
        parent_id=None,
        child_ids=(),
        own_block_indexes=blocks,
        heading_path=(),
        ordinal_in_parent=0,
        occurrence=0,
        content_hash="h",
        title="t",
    )


def test_wrapping_counts_lines() -> None:
    sizer = HeuristicSizeEstimator(char_width=10.0, line_height=20.0)
    assert sizer.lines_for("abcde", width=100.0) == 1
    assert sizer.lines_for("a" * 45, width=100.0) == 5


def test_explicit_newlines_each_count() -> None:
    sizer = HeuristicSizeEstimator()
    assert sizer.lines_for("a\nb\nc", width=1000.0) == 3


def test_longer_text_is_taller() -> None:
    sizer = HeuristicSizeEstimator()
    blocks: Mapping[int, Block] = {0: block(0, "short"), 1: block(1, "word " * 200)}
    short = sizer.estimate_height(card(CardKind.FALLBACK_TEXT, (0,)), blocks=blocks, width=400)
    long = sizer.estimate_height(card(CardKind.FALLBACK_TEXT, (1,)), blocks=blocks, width=400)
    assert long > short


def test_empty_card_still_has_one_line() -> None:
    sizer = HeuristicSizeEstimator()
    assert sizer.estimate_height(card(CardKind.FALLBACK_TEXT, ()), blocks={}, width=400) > 0


def test_missing_block_indexes_are_ignored() -> None:
    sizer = HeuristicSizeEstimator()
    assert sizer.estimate_height(card(CardKind.FALLBACK_TEXT, (99,)), blocks={}, width=400) > 0


def test_the_cards_own_heading_is_not_a_body_line() -> None:
    """The header bar draws the title, so the heading block must not add a body line (E-029).

    Counting it made every heading card one line too tall, which is what pushed a gap between a
    parent card's text and its first child (measured 56 px where 36 px was intended).
    """
    sizer = HeuristicSizeEstimator()
    heading = Block(index=0, kind=BlockKind.HEADING, raw_text="# Title", text_normalized="# Title")
    blocks: Mapping[int, Block] = {0: heading, 1: block(1, "body")}
    with_heading = sizer.estimate_height(card(CardKind.HEADING, (0, 1)), blocks=blocks, width=400)
    without_heading = sizer.estimate_height(card(CardKind.HEADING, (1,)), blocks=blocks, width=400)
    assert with_heading == without_heading


def test_rich_card_kinds_get_extra_room() -> None:
    sizer = HeuristicSizeEstimator()
    blocks: Mapping[int, Block] = {0: block(0, "same text")}
    text = sizer.estimate_height(card(CardKind.FALLBACK_TEXT, (0,)), blocks=blocks, width=400)
    image = sizer.estimate_height(card(CardKind.IMAGE, (0,)), blocks=blocks, width=400)
    assert image > text


def test_a_toc_card_is_sized_by_its_generated_entries() -> None:
    """T-021: the card draws one line per heading, not the one-line ``[TOC]`` marker."""
    sizer = HeuristicSizeEstimator(char_width=10.0, line_height=20.0)
    marker = Block(
        index=0,
        kind=BlockKind.TOC,
        raw_text="[TOC]",
        text_normalized="[TOC]",
        attrs={TOC_ENTRIES_ATTR: "6"},
    )
    height = sizer.estimate_height(card(CardKind.TOC, (0,)), blocks={0: marker}, width=400)
    assert height >= 6 * 20.0

    plain = Block(index=1, kind=BlockKind.TOC, raw_text="[TOC]", text_normalized="[TOC]")
    short = sizer.estimate_height(card(CardKind.TOC, (1,)), blocks={1: plain}, width=400)
    assert short < height, "without the stamp the marker itself is one line"


def test_a_broken_toc_stamp_falls_back_to_one_line() -> None:
    sizer = HeuristicSizeEstimator()
    weird = Block(
        index=0,
        kind=BlockKind.TOC,
        raw_text="[TOC]",
        text_normalized="[TOC]",
        attrs={TOC_ENTRIES_ATTR: "many"},
    )
    assert sizer.estimate_height(card(CardKind.TOC, (0,)), blocks={0: weird}, width=400) > 0
