"""Tests for the measured-height estimator adapter (T-049)."""

from __future__ import annotations

from collections.abc import Mapping

from mcwr.domain.enums import BlockKind, CardKind
from mcwr.domain.models import Block, Card
from mcwr.infrastructure.heuristic_sizer import HeuristicSizeEstimator
from mcwr.infrastructure.measured_sizer import MeasuredHeightEstimator


def _block(index: int, text: str) -> Block:
    return Block(index=index, kind=BlockKind.PARAGRAPH, raw_text=text, text_normalized=text)


def _card(kind: CardKind, blocks: tuple[int, ...], card_id: str = "c") -> Card:
    return Card(
        card_id=card_id,
        kind=kind,
        parent_id=None,
        child_ids=(),
        own_block_indexes=blocks,
        heading_path=(),
        ordinal_in_parent=0,
        occurrence=0,
        content_hash="h",
        title="t",
    )


def test_a_measured_card_uses_its_measured_height() -> None:
    estimator = MeasuredHeightEstimator(HeuristicSizeEstimator(), {"c": 123.0})
    measured = estimator.estimate_height(_card(CardKind.FALLBACK_TEXT, ()), blocks={}, width=400.0)
    assert measured == 123.0


def test_a_card_without_a_measurement_falls_back_to_the_heuristic() -> None:
    fallback = HeuristicSizeEstimator()
    estimator = MeasuredHeightEstimator(fallback, {"another-card": 123.0})
    blocks: Mapping[int, Block] = {0: _block(0, "some body text")}
    unmeasured = _card(CardKind.FALLBACK_TEXT, (0,))
    assert estimator.estimate_height(unmeasured, blocks=blocks, width=400.0) == (
        fallback.estimate_height(unmeasured, blocks=blocks, width=400.0)
    )


def test_a_measurement_of_zero_is_respected() -> None:
    """An empty body legitimately measures 0; only a missing key falls back."""
    estimator = MeasuredHeightEstimator(HeuristicSizeEstimator(), {"c": 0.0})
    assert estimator.estimate_height(_card(CardKind.FALLBACK_TEXT, ()), blocks={}, width=400.0) == 0
