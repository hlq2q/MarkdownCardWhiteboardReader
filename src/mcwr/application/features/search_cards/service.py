"""Case-sensitive text search over the cards of one document (T-019).

Semantics are the user's answers (2026-10-12): the query matches **case-sensitively** against
each card's **own body text** — its own blocks plus, when a card has no block carrying it, its
title. A card's own content is exactly what it draws (D-005), so a hit is something the reader
can actually see in that card, and a parent never matches text that lives in its children.

No regex, no fuzzy matching: a plain substring, which keeps results explainable.
"""

from __future__ import annotations

from collections.abc import Mapping

from mcwr.application.features.search_cards.models import SearchHit
from mcwr.domain.models import Block, Card, CardTree


def card_text(card: Card, blocks: Mapping[int, Block]) -> str:
    """The text one card contributes to a search: its own blocks, plus its title if unseen.

    The title is added only when the own blocks do not already contain it: a heading card's
    title *is* its heading text, and counting both would report one visible occurrence twice.
    A code card's title (its language) is usually absent from the code itself, and searching
    for the language is useful.
    """
    parts = [
        block.raw_text or block.text_normalized
        for index in card.own_block_indexes
        if (block := blocks.get(index)) is not None
    ]
    text = "\n".join(parts)
    if card.title and card.title not in text:
        return f"{card.title}\n{text}" if text else card.title
    return text


def search_cards(
    tree: CardTree, blocks: Mapping[int, Block], query: str
) -> tuple[SearchHit, ...]:
    """Cards whose own text contains ``query``, in document order.

    An empty query matches nothing (the caller decides what to say about that); a query that
    matches no card returns an empty tuple, never ``None``.
    """
    if not query:
        return ()
    hits: list[SearchHit] = []
    for card_id in tree.ordered_ids():
        card = tree.cards[card_id]
        occurrences = card_text(card, blocks).count(query)
        if occurrences:
            hits.append(SearchHit(card_id=card_id, title=card.title, matches=occurrences))
    return tuple(hits)
