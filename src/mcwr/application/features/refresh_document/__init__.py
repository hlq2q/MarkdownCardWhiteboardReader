"""Feature slice: merge a re-parsed document into the current board (FR-5, D11)."""

from __future__ import annotations

from mcwr.application.features.refresh_document.models import (
    CardMapping,
    RefreshPlan,
    StructureSignature,
)
from mcwr.application.features.refresh_document.service import (
    is_major_change,
    major_change_warnings,
    match_cards,
    merge_layouts,
    plan_refresh,
    structure_signature,
)

__all__ = [
    "CardMapping",
    "RefreshPlan",
    "StructureSignature",
    "is_major_change",
    "major_change_warnings",
    "match_cards",
    "merge_layouts",
    "plan_refresh",
    "structure_signature",
]
