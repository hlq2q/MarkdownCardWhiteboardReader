"""DTO of the build_toc slice (FR-2.4 / F10)."""

from __future__ import annotations

from dataclasses import dataclass

from mcwr.domain.models import CardId


@dataclass(frozen=True, slots=True)
class TocEntry:
    """One clickable table-of-contents line, pointing at a heading card."""

    card_id: CardId
    label: str
    anchor: str
    level: int
