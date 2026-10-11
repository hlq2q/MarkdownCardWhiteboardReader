"""Tests for the parse_document use case, using hand-written fakes (no mocks)."""

from __future__ import annotations

from pathlib import Path

from mcwr.application.features.parse_document.models import SourceText
from mcwr.application.features.parse_document.service import parse_document
from mcwr.domain.enums import BlockKind
from mcwr.domain.errors import DocumentMissingError
from mcwr.domain.models import Block


class FakeReader:
    def __init__(self, source: SourceText | Exception) -> None:
        self._source = source
        self.read_paths: list[Path] = []

    def read(self, path: Path) -> SourceText:
        self.read_paths.append(path)
        if isinstance(self._source, Exception):
            raise self._source
        return self._source


class FakeParser:
    def __init__(self, blocks: tuple[Block, ...] | Exception) -> None:
        self._blocks = blocks
        self.seen: list[str] = []

    def parse(self, text: str) -> tuple[Block, ...]:
        self.seen.append(text)
        if isinstance(self._blocks, Exception):
            raise self._blocks
        return self._blocks


def _source(text: str = "# Title\n") -> SourceText:
    return SourceText(
        text=text,
        encoding="utf-8",
        newline="\n",
        size=len(text.encode("utf-8")),
        mtime=1234.5,
    )


def _block(index: int = 0) -> Block:
    return Block(
        index=index,
        kind=BlockKind.HEADING,
        raw_text="# Title",
        text_normalized="Title",
        level=1,
    )


def test_parses_and_builds_the_document_key(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    parsed = parse_document(path, reader=FakeReader(_source()), parser=FakeParser((_block(),)))
    assert parsed.blocks == (_block(),)
    assert parsed.document.path == path
    assert parsed.document.size == len("# Title\n")
    assert parsed.document.mtime == 1234.5
    assert parsed.document.path_hash
    assert parsed.document.content_hash
    assert parsed.warnings == ()


def test_reader_warnings_are_forwarded(tmp_path: Path) -> None:
    source = SourceText(
        text="x", encoding="gbk", newline="\n", size=1, mtime=0.0, warnings=("decoded as gbk",)
    )
    parsed = parse_document(
        tmp_path / "d.md", reader=FakeReader(source), parser=FakeParser((_block(),))
    )
    assert parsed.warnings == ("decoded as gbk",)


def test_content_edits_change_the_hash_but_not_the_parser_contract(tmp_path: Path) -> None:
    first = parse_document(
        tmp_path / "a.md", reader=FakeReader(_source("# A\n")), parser=FakeParser((_block(),))
    )
    second = parse_document(
        tmp_path / "a.md", reader=FakeReader(_source("# B\n")), parser=FakeParser((_block(),))
    )
    assert first.document.content_hash != second.document.content_hash


def test_parser_failure_degrades_to_plain_text(tmp_path: Path) -> None:
    parsed = parse_document(
        tmp_path / "broken.md",
        reader=FakeReader(_source("# Title\n\ntext\n")),
        parser=FakeParser(RuntimeError("boom")),
    )
    assert len(parsed.blocks) == 1
    assert parsed.blocks[0].kind is BlockKind.UNKNOWN
    assert parsed.blocks[0].raw_text == "# Title\n\ntext\n"
    assert any("parser failed" in warning for warning in parsed.warnings)


def test_missing_file_propagates_the_domain_error(tmp_path: Path) -> None:
    reader = FakeReader(DocumentMissingError("gone"))
    try:
        parse_document(tmp_path / "gone.md", reader=reader, parser=FakeParser(()))
    except DocumentMissingError:
        pass
    else:  # pragma: no cover - the call must raise
        raise AssertionError("expected DocumentMissingError")


def test_parser_receives_the_decoded_text(tmp_path: Path) -> None:
    parser = FakeParser((_block(),))
    parse_document(tmp_path / "d.md", reader=FakeReader(_source("# Decoded\n")), parser=parser)
    assert parser.seen == ["# Decoded\n"]
