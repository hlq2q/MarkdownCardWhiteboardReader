"""Estimator adapter: prefer the height a card really rendered, fall back to the text heuristic.

The layout is pure and cannot measure a QTextDocument, so the view measures its items once they
exist and hands the numbers back (T-049). Cards the view cannot measure -- the kinds whose body is
a rendered image -- keep the heuristic's guess.
"""

from __future__ import annotations

from collections.abc import Mapping

from mcwr.application.features.layout_board.ports import SizeEstimator
from mcwr.domain.models import Block, Card, CardId


class MeasuredHeightEstimator:
    """``estimate_height`` from the measured map when the card is in it, else from ``fallback``."""

    def __init__(self, fallback: SizeEstimator, measured: Mapping[CardId, float]) -> None:
        self._fallback = fallback
        self._measured = measured

    def estimate_height(self, card: Card, *, blocks: Mapping[int, Block], width: float) -> float:
        known = self._measured.get(card.card_id)
        if known is not None:
            return known
        return self._fallback.estimate_height(card, blocks=blocks, width=width)
