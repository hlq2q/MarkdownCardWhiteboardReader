"""DTO of the load_document slice."""

from __future__ import annotations

from dataclasses import dataclass

from mcwr.domain.models import MAX_CARDS, Block, CardTree, DocumentKey


@dataclass(frozen=True, slots=True)
class LoadedDocument:
    """Everything the UI or CLI needs after opening a file, before any layout."""

    document: DocumentKey
    blocks: tuple[Block, ...]
    tree: CardTree
    warnings: tuple[str, ...] = ()

    @property
    def card_count(self) -> int:
        """How many cards this document produced (T-025 acceptance ①)."""
        return len(self.tree.cards)

    @property
    def over_limit(self) -> bool:
        """Whether the document is larger than :data:`~mcwr.domain.models.MAX_CARDS`.

        The flag is computed from the tree, never stored, so it cannot drift out of sync
        with the card count it describes (D-023/D-029).
        """
        return self.card_count > MAX_CARDS
