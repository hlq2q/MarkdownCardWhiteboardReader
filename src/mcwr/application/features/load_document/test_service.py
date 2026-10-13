"""Tests for the load_document use case (fakes, no real parser)."""

from __future__ import annotations

from pathlib import Path

from mcwr.application.features.load_document.models import LoadedDocument
from mcwr.application.features.load_document.service import load_document
from mcwr.application.features.parse_document.models import SourceText
from mcwr.domain.enums import BlockKind
from mcwr.domain.ids import normalize_text
from mcwr.domain.models import MAX_CARDS, Block


class FakeReader:
    def __init__(self, text: str, warnings: tuple[str, ...] = ()) -> None:
        self._source = SourceText(
            text=text,
            encoding="utf-8",
            newline="\n",
            size=len(text.encode("utf-8")),
            mtime=7.0,
            warnings=warnings,
        )
        self.read_paths: list[Path] = []

    def read(self, path: Path) -> SourceText:
        self.read_paths.append(path)
        return self._source


class FakeParser:
    def __init__(self, blocks: tuple[Block, ...]) -> None:
        self._blocks = blocks
        self.seen_text: list[str] = []

    def parse(self, text: str) -> tuple[Block, ...]:
        self.seen_text.append(text)
        return self._blocks


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


def divider(index: int) -> Block:
    return Block(
        index=index,
        kind=BlockKind.THEMATIC_BREAK,
        raw_text="---",
        text_normalized="---",
    )


def test_loads_a_tree_and_carries_warnings(tmp_path: Path) -> None:
    blocks = (heading(0, "A", 1), paragraph(1, "body"))
    loaded = load_document(
        tmp_path / "doc.md",
        reader=FakeReader("# A\n\nbody\n", warnings=("decoded as gbk",)),
        parser=FakeParser(blocks),
    )
    assert len(loaded.tree.root_ids) == 1
    assert loaded.warnings == ("decoded as gbk",)
    assert loaded.document.path == tmp_path / "doc.md"
    assert loaded.blocks == blocks


def test_dividers_produce_several_big_sections(tmp_path: Path) -> None:
    blocks = (heading(0, "A", 1), divider(1), heading(2, "B", 1))
    loaded = load_document(tmp_path / "doc.md", reader=FakeReader("x"), parser=FakeParser(blocks))
    assert len(loaded.tree.root_ids) == 2
    titles = [loaded.tree.cards[root].title for root in loaded.tree.root_ids]
    assert titles == ["Section 1", "Section 2"]


def test_content_edit_changes_hash_but_not_card_ids(tmp_path: Path) -> None:
    before = load_document(
        tmp_path / "doc.md",
        reader=FakeReader("v1"),
        parser=FakeParser((heading(0, "A", 1), paragraph(1, "one"))),
    )
    after = load_document(
        tmp_path / "doc.md",
        reader=FakeReader("v2"),
        parser=FakeParser((heading(0, "A", 1), paragraph(1, "two"))),
    )
    assert before.tree.ordered_ids() == after.tree.ordered_ids()
    assert before.document.content_hash != after.document.content_hash


# --------------------------------------------------------------- card limit (T-025)


def _headings(count: int) -> tuple[Block, ...]:
    """``count`` heading cards, each with one paragraph of its own content."""
    blocks: list[Block] = []
    for index in range(count):
        blocks.append(heading(index * 2, f"H{index}", 1))
        blocks.append(paragraph(index * 2 + 1, f"body {index}"))
    return tuple(blocks)


def _load(tmp_path: Path, headings: int) -> LoadedDocument:
    return load_document(
        tmp_path / "doc.md",
        reader=FakeReader("x"),
        parser=FakeParser(_headings(headings)),
    )


def test_the_product_limit_is_two_hundred_cards() -> None:
    """Pins the D-023 value; a change here must be a deliberate decision, not a drift."""
    assert MAX_CARDS == 200


def test_a_document_at_the_limit_is_not_flagged(tmp_path: Path) -> None:
    loaded = _load(tmp_path, MAX_CARDS - 1)  # + the implicit big-section card = 200
    assert loaded.card_count == MAX_CARDS
    assert loaded.over_limit is False


def test_one_card_more_than_the_limit_is_flagged(tmp_path: Path) -> None:
    loaded = _load(tmp_path, MAX_CARDS)  # 201 cards
    assert loaded.card_count == MAX_CARDS + 1
    assert loaded.over_limit is True
