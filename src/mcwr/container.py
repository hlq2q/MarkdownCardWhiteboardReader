"""Dependency assembly — the only place allowed to construct concrete adapters."""

from __future__ import annotations

from pathlib import Path

from mcwr.application.features.load_document.models import LoadedDocument
from mcwr.application.features.load_document.service import load_document as _load_document
from mcwr.application.features.parse_document.ports import BlockParser, MarkdownReader
from mcwr.infrastructure.markdown_it_adapter import MarkdownItBlockParser
from mcwr.infrastructure.markdown_reader import FileMarkdownReader


def build_reader() -> MarkdownReader:
    return FileMarkdownReader()


def build_parser() -> BlockParser:
    return MarkdownItBlockParser()


def load(path: Path) -> LoadedDocument:
    """Open ``path`` with the production adapters."""
    return _load_document(path, reader=build_reader(), parser=build_parser())


def load_with(path: Path, *, reader: MarkdownReader, parser: BlockParser) -> LoadedDocument:
    """Open ``path`` with injected adapters (tests, spikes, future GUI sessions)."""
    return _load_document(path, reader=reader, parser=parser)
