"""Ports of the layout_board slice."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from mcwr.domain.models import Block, Card


class SizeEstimator(Protocol):
    """Estimates how tall a card's own content is at a given inner width.

    Kept behind a port because the real answer comes from font metrics (a platform
    concern); tests inject a deterministic fake.
    """

    def estimate_height(
        self, card: Card, *, blocks: Mapping[int, Block], width: float
    ) -> float: ...
