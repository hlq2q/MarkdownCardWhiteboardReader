"""Tests for the markdown-it adapter, driven by the spike sample document."""

from __future__ import annotations

from pathlib import Path

from mcwr.domain.enums import BlockKind
from mcwr.domain.models import TOC_ENTRIES_ATTR, Block
from mcwr.infrastructure.markdown_it_adapter import MarkdownItBlockParser

SAMPLE = Path(__file__).resolve().parents[3] / "spikes" / "samples" / "sample.md"


def parse_sample() -> tuple[tuple[BlockKind, ...], dict[int, Block]]:
    text = SAMPLE.read_text(encoding="utf-8")
    blocks = MarkdownItBlockParser().parse(text)
    by_index = {block.index: block for block in blocks}
    return tuple(block.kind for block in blocks), by_index


def test_indexes_are_sequential() -> None:
    kinds, by_index = parse_sample()
    assert len(kinds) == len(by_index)
    assert sorted(by_index) == list(range(len(kinds)))


def test_every_block_keeps_its_raw_text() -> None:
    _, by_index = parse_sample()
    empty = [block.index for block in by_index.values() if not block.raw_text]
    assert empty == [], f"blocks lost their raw text: {empty}"


def test_expected_block_kinds_are_all_present() -> None:
    kinds, _ = parse_sample()
    for expected in (
        BlockKind.HEADING,
        BlockKind.PARAGRAPH,
        BlockKind.BLOCKQUOTE,
        BlockKind.LIST,
        BlockKind.TASK_LIST,
        BlockKind.TABLE,
        BlockKind.CODE,
        BlockKind.MERMAID,
        BlockKind.MATH_BLOCK,
        BlockKind.IMAGE,
        BlockKind.TOC,
        BlockKind.THEMATIC_BREAK,
        BlockKind.HTML,
    ):
        assert expected in kinds, f"missing block kind {expected}"


def test_headings_carry_levels_and_text() -> None:
    _, by_index = parse_sample()
    headings = [block for block in by_index.values() if block.kind is BlockKind.HEADING]
    levels = [block.level for block in headings]
    assert levels[:2] == [1, 2]
    assert max(level for level in levels if level is not None) == 3
    titles = {block.text_normalized for block in headings}
    assert {"Task list", "Table", "Code", "Mermaid", "Math", "Images", "TOC"} <= titles


def test_code_and_mermaid_are_split_by_language() -> None:
    _, by_index = parse_sample()
    code = [block for block in by_index.values() if block.kind is BlockKind.CODE]
    mermaid = [block for block in by_index.values() if block.kind is BlockKind.MERMAID]
    assert [block.lang for block in code] == ["python"]
    assert "def hello" in code[0].text_normalized
    assert mermaid[0].lang == "mermaid"
    assert "graph TD" in mermaid[0].text_normalized


def test_math_block_and_inline_math() -> None:
    _, by_index = parse_sample()
    math = [block for block in by_index.values() if block.kind is BlockKind.MATH_BLOCK]
    assert math[0].text_normalized == "E = mc^2"
    inline_kinds = {span.kind for block in by_index.values() for span in block.inline}
    assert "math" in inline_kinds


def test_task_list_counts_checked_items() -> None:
    _, by_index = parse_sample()
    tasks = [block for block in by_index.values() if block.kind is BlockKind.TASK_LIST]
    assert tasks[0].attrs["checked"] == "1"
    assert tasks[0].attrs["total"] == "2"


def test_plain_list_is_not_a_card_block() -> None:
    _, by_index = parse_sample()
    lists = [block for block in by_index.values() if block.kind is BlockKind.LIST]
    assert lists, "ordered list must be recognised as content"
    assert lists[0].attrs == {}


def test_toc_marker_becomes_a_toc_block() -> None:
    _, by_index = parse_sample()
    toc = [block for block in by_index.values() if block.kind is BlockKind.TOC]
    assert toc[0].text_normalized == "[TOC]"


def test_a_toc_block_records_how_many_entries_it_will_list() -> None:
    """T-021: the card is sized by the generated entries, so the count travels in the IR."""
    text = "# One\n\n[TOC]\n\n## Two\n\n### Three\n"
    blocks = MarkdownItBlockParser().parse(text)
    toc = [block for block in blocks if block.kind is BlockKind.TOC][0]
    headings = [block for block in blocks if block.kind is BlockKind.HEADING]
    assert toc.attrs[TOC_ENTRIES_ATTR] == "3"
    assert toc.attrs[TOC_ENTRIES_ATTR] == str(len(headings))


def test_a_document_without_headings_carries_no_stamp() -> None:
    blocks = MarkdownItBlockParser().parse("[TOC]\n\njust prose\n")
    toc = [block for block in blocks if block.kind is BlockKind.TOC][0]
    assert TOC_ENTRIES_ATTR not in toc.attrs


def test_image_paragraph_becomes_an_image_block_with_attributes() -> None:
    _, by_index = parse_sample()
    images = [block for block in by_index.values() if block.kind is BlockKind.IMAGE]
    assert images[0].attrs["src"] == "images/diagram.png"


def test_table_and_html_and_divider() -> None:
    _, by_index = parse_sample()
    table = [block for block in by_index.values() if block.kind is BlockKind.TABLE][0]
    assert "Column A" in table.text_normalized
    html = [block for block in by_index.values() if block.kind is BlockKind.HTML][0]
    assert html.raw_text.startswith("<div")
    divider = [block for block in by_index.values() if block.kind is BlockKind.THEMATIC_BREAK][0]
    assert divider.raw_text.startswith("---")


def test_source_spans_point_at_real_lines() -> None:
    text = SAMPLE.read_text(encoding="utf-8")
    lines = text.splitlines()
    _, by_index = parse_sample()
    for block in by_index.values():
        if block.span is None:
            continue
        assert 1 <= block.span.start_line <= len(lines)
        assert block.span.start_line <= block.span.end_line <= len(lines)


def test_empty_document_yields_no_blocks() -> None:
    assert MarkdownItBlockParser().parse("") == ()


def test_unclosed_container_does_not_raise() -> None:
    parser = MarkdownItBlockParser()
    assert parser.parse("> quote\n\n- item\n\n| a |\n| - |\n| 1 |\n") is not None
