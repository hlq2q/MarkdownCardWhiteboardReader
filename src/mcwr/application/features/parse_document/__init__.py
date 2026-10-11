"""Feature slice: read and parse one Markdown file into blocks (IR)."""

from __future__ import annotations

from mcwr.application.features.parse_document.models import ParsedDocument, SourceText
from mcwr.application.features.parse_document.ports import BlockParser, MarkdownReader
from mcwr.application.features.parse_document.service import parse_document

__all__ = ["BlockParser", "MarkdownReader", "ParsedDocument", "SourceText", "parse_document"]
