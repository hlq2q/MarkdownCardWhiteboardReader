"""Tests for the read-only file reader (FR-1.6, FR-8.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcwr.domain.errors import DocumentDecodeError, DocumentMissingError
from mcwr.infrastructure.markdown_reader import FileMarkdownReader


def test_reads_utf8_and_reports_metadata(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    # Bytes, not text mode: Windows text mode would rewrite "\n" into "\r\n".
    path.write_bytes("# 标题\n\n正文\n".encode())
    source = FileMarkdownReader().read(path)
    assert "# 标题" in source.text
    assert source.encoding == "utf-8"
    assert source.warnings == ()
    assert source.size == path.stat().st_size
    assert source.newline == "\n"


def test_reads_utf8_bom_without_leaking_the_bom(tmp_path: Path) -> None:
    path = tmp_path / "bom.md"
    path.write_bytes("\ufeff# Title\n".encode("utf-8"))
    source = FileMarkdownReader().read(path)
    assert source.encoding == "utf-8-sig"
    assert source.text.startswith("# Title")
    assert "\ufeff" not in source.text


def test_reads_gbk_and_warns(tmp_path: Path) -> None:
    path = tmp_path / "gbk.md"
    path.write_bytes("# 中文标题\n".encode("gbk"))
    source = FileMarkdownReader().read(path)
    assert source.encoding == "gbk"
    assert "中文标题" in source.text
    assert any("gbk" in warning for warning in source.warnings)


def test_detects_crlf(tmp_path: Path) -> None:
    path = tmp_path / "crlf.md"
    path.write_bytes(b"line one\r\nline two\r\n")
    assert FileMarkdownReader().read(path).newline == "\r\n"


def test_missing_file_raises_domain_error(tmp_path: Path) -> None:
    with pytest.raises(DocumentMissingError):
        FileMarkdownReader().read(tmp_path / "nope.md")


def test_directory_raises_domain_error(tmp_path: Path) -> None:
    with pytest.raises(DocumentMissingError):
        FileMarkdownReader().read(tmp_path)


def test_undecodable_bytes_degrade_with_replacement_characters(tmp_path: Path) -> None:
    """FR-1.6 / NFR-4: bad bytes never block the open, they warn and show best effort."""
    path = tmp_path / "weird.md"
    path.write_bytes(b"\xff\xfe\x00\x01\x80\x81")
    source = FileMarkdownReader(candidates=("utf-8", "ascii")).read(path)
    assert source.encoding == "utf-8"
    assert "\ufffd" in source.text
    assert any("replacement characters" in warning for warning in source.warnings)


def test_empty_candidate_list_is_a_programming_error(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(DocumentDecodeError):
        FileMarkdownReader(candidates=()).read(path)


def test_reading_never_touches_the_source_directory(tmp_path: Path) -> None:
    """FR-8.2: the source file and its directory must be untouched by a read."""
    path = tmp_path / "doc.md"
    path.write_text("# Title\n\ntext\n", encoding="utf-8")
    before = path.stat()
    listing_before = sorted(entry.name for entry in tmp_path.iterdir())

    FileMarkdownReader().read(path)

    after = path.stat()
    assert listing_before == sorted(entry.name for entry in tmp_path.iterdir())
    assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)
