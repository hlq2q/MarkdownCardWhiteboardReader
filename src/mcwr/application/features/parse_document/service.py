"""Use case: read + parse one Markdown document, degrading instead of crashing (FR-1.5)."""

from __future__ import annotations

from pathlib import Path

from mcwr.application.features.parse_document.models import ParsedDocument, SourceText
from mcwr.application.features.parse_document.ports import BlockParser, MarkdownReader
from mcwr.domain.enums import BlockKind
from mcwr.domain.ids import content_hash, document_path_hash, normalize_text
from mcwr.domain.models import Block, DocumentKey


def fallback_block(text: str) -> Block:
    """One plain-text block standing in for a document whose parser failed."""
    return Block(
        index=0,
        kind=BlockKind.UNKNOWN,
        raw_text=text,
        text_normalized=normalize_text(text),
    )


def _document_key(path: Path, source: SourceText) -> DocumentKey:
    return DocumentKey(
        path=path,
        path_hash=document_path_hash(path),
        size=source.size,
        mtime=source.mtime,
        content_hash=content_hash(source.text),
    )


def parse_document(
    path: Path,
    *,
    reader: MarkdownReader,
    parser: BlockParser,
) -> ParsedDocument:
    """Read ``path`` and turn it into blocks.

    A failing parser degrades to a single plain-text block with a warning attached;
    a missing or undecodable file raises a domain error for the caller to surface.
    """
    source = reader.read(path)
    try:
        blocks = parser.parse(source.text)
    except Exception as exc:  # noqa: BLE001 - acceptance 10: never crash on bad input
        warning = f"parser failed ({type(exc).__name__}: {exc}); shown as plain text"
        return ParsedDocument(
            document=_document_key(path, source),
            blocks=(fallback_block(source.text),),
            warnings=(*source.warnings, warning),
        )
    return ParsedDocument(
        document=_document_key(path, source),
        blocks=blocks,
        warnings=source.warnings,
    )
