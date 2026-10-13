"""Tests for the TOC slice: entries, anchors and the click mapping (FR-2.4, D-025).

Pure: blocks go in, entries come out; no Qt, no filesystem.
"""

from __future__ import annotations

from mcwr.application.features.build_card_tree.service import build_card_tree
from mcwr.application.features.build_toc.service import (
    EMPTY_TOC_TEXT,
    build_toc,
    resolve_anchor,
    slugify,
    toc_markdown,
)
from mcwr.domain.enums import BlockKind
from mcwr.domain.ids import normalize_text
from mcwr.domain.models import Block, CardTree

PATH_HASH = "deadbeef"


def heading(index: int, text: str, level: int) -> Block:
    return Block(
        index=index,
        kind=BlockKind.HEADING,
        raw_text=text,
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


def toc_marker(index: int) -> Block:
    return Block(index=index, kind=BlockKind.TOC, raw_text="[TOC]", text_normalized="[TOC]")


def _tree(*blocks: Block) -> CardTree:
    return build_card_tree(blocks, path_hash=PATH_HASH)


def test_slugify_follows_the_github_shape() -> None:
    assert slugify("Hello, World!") == "hello-world"
    assert slugify("  spaced   out  ") == "spaced-out"
    assert slugify("A--B") == "a-b"
    assert slugify("中文 标题") == "中文-标题"
    assert slugify("café") == "café"
    assert slugify("!!!") == "section", "an empty slug must still be addressable"


def test_every_heading_level_becomes_an_entry_in_document_order() -> None:
    tree = _tree(
        heading(0, "One", 1),
        paragraph(1, "body"),
        heading(2, "Two", 2),
        heading(3, "Three", 3),
        heading(4, "Deep", 6),
    )
    entries = build_toc(tree)
    assert [entry.label for entry in entries] == ["One", "Two", "Three", "Deep"]
    assert [entry.level for entry in entries] == [1, 2, 3, 6]
    assert [entry.anchor for entry in entries] == ["one", "two", "three", "deep"]


def test_duplicate_titles_stay_separately_addressable() -> None:
    tree = _tree(heading(0, "Notes", 1), heading(1, "Notes", 1), heading(2, "Notes", 2))
    entries = build_toc(tree)
    assert [entry.anchor for entry in entries] == ["notes", "notes-1", "notes-2"]
    assert len({entry.card_id for entry in entries}) == 3


def test_the_toc_marker_itself_is_never_an_entry() -> None:
    tree = _tree(toc_marker(0), heading(1, "One", 1))
    entries = build_toc(tree)
    assert [entry.label for entry in entries] == ["One"]


def test_resolve_anchor_accepts_the_hash_prefix_and_rejects_unknown() -> None:
    tree = _tree(heading(0, "One", 1), heading(1, "Notes", 1), heading(2, "Notes", 1))
    entries = build_toc(tree)
    assert resolve_anchor(entries, "#notes-1") == entries[2].card_id
    assert resolve_anchor(entries, "  #one ") == entries[0].card_id
    assert resolve_anchor(entries, "missing") is None
    assert resolve_anchor(entries, "#") is None
    assert resolve_anchor((), "#one") is None


def test_the_body_indents_by_level_and_links_every_anchor() -> None:
    tree = _tree(heading(0, "One", 1), heading(1, "Two", 2))
    body = toc_markdown(build_toc(tree))
    assert body == "- [One](#one)\n  - [Two](#two)"


def test_a_document_without_headings_says_so_instead_of_showing_nothing() -> None:
    tree = _tree(paragraph(0, "just prose"), toc_marker(1))
    assert build_toc(tree) == ()
    assert toc_markdown(()) == EMPTY_TOC_TEXT
