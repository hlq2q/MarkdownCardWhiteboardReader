"""DTO of the detach_restore slice."""

from __future__ import annotations

from dataclasses import dataclass, field

from mcwr.domain.models import CardId


@dataclass(frozen=True, slots=True)
class LayoutChange:
    """What a view-state operation changed, so the caller knows what to redraw.

    ``affected``   cards whose view state actually changed (empty = the call was a no-op)
    ``blocked``    cards the operation refuses to touch, with the reason in ``reason``
    ``relayout``   whether the caller must re-stack the affected subtree
    ``reason``     human-readable explanation, empty when nothing was blocked
    """

    affected: tuple[CardId, ...] = ()
    blocked: tuple[CardId, ...] = ()
    relayout: bool = False
    reason: str = ""

    @property
    def changed(self) -> bool:
        return bool(self.affected)

    @property
    def relayout_roots(self) -> tuple[CardId, ...]:
        """Cards whose subtree must be re-stacked (the affected cards themselves)."""
        return self.affected if self.relayout else ()

    def merged_with(self, other: LayoutChange) -> LayoutChange:
        """Union of two changes, keeping the first non-empty reason."""
        return LayoutChange(
            affected=tuple(dict.fromkeys((*self.affected, *other.affected))),
            blocked=tuple(dict.fromkeys((*self.blocked, *other.blocked))),
            relayout=self.relayout or other.relayout,
            reason=self.reason or other.reason,
        )


@dataclass(slots=True)
class ChangeAccumulator:
    """Mutable helper so the small operations below stay under the line budget."""

    affected: list[CardId] = field(default_factory=list)
    blocked: list[CardId] = field(default_factory=list)
    relayout: bool = False
    reason: str = ""

    def add(self, card_id: CardId) -> None:
        if card_id not in self.affected:
            self.affected.append(card_id)

    def block(self, card_id: CardId, reason: str) -> None:
        if card_id not in self.blocked:
            self.blocked.append(card_id)
        self.reason = self.reason or reason

    def result(self) -> LayoutChange:
        return LayoutChange(
            affected=tuple(self.affected),
            blocked=tuple(self.blocked),
            relayout=self.relayout,
            reason=self.reason,
        )
