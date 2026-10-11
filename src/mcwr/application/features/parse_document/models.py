"""DTOs of the parse_document slice."""

from __future__ import annotations

from dataclasses import dataclass

from mcwr.domain.models import Block, DocumentKey


@dataclass(frozen=True, slots=True)
class SourceText:
    """Raw file content plus how it was decoded (never mutates the source)."""

    text: str
    encoding: str
    newline: str
    size: int
    mtime: float
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """One read of one document: its key plus the block sequence (IR)."""

    document: DocumentKey
    blocks: tuple[Block, ...]
    warnings: tuple[str, ...] = ()
