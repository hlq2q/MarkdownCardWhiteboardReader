"""Ports of the parse_document slice (implemented by infrastructure adapters)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from mcwr.application.features.parse_document.models import SourceText
from mcwr.domain.models import Block


class MarkdownReader(Protocol):
    """Reads bytes from disk and decodes them. Never writes anywhere."""

    def read(self, path: Path) -> SourceText: ...


class BlockParser(Protocol):
    """Turns decoded Markdown text into the block sequence (IR)."""

    def parse(self, text: str) -> tuple[Block, ...]: ...
