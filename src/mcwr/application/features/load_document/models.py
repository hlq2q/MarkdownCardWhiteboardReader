"""DTO of the load_document slice."""

from __future__ import annotations

from dataclasses import dataclass

from mcwr.domain.models import Block, CardTree, DocumentKey


@dataclass(frozen=True, slots=True)
class LoadedDocument:
    """Everything the UI or CLI needs after opening a file, before any layout."""

    document: DocumentKey
    blocks: tuple[Block, ...]
    tree: CardTree
    warnings: tuple[str, ...] = ()
