"""DTO of the persist_layout slice."""

from __future__ import annotations

from dataclasses import dataclass

from mcwr.domain.models import BoardSnapshot


@dataclass(frozen=True, slots=True)
class RestoredLayout:
    """What restore_snapshot produced: a usable snapshot plus the warnings to surface."""

    snapshot: BoardSnapshot
    warnings: tuple[str, ...] = ()
