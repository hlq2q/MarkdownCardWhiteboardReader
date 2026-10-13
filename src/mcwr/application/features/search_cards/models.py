"""DTO of the search_cards slice (V1.1, T-019)."""

from __future__ import annotations

from dataclasses import dataclass

from mcwr.domain.models import CardId


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One matching card: how it is labelled and how often the query occurs in it."""

    card_id: CardId
    title: str
    matches: int
