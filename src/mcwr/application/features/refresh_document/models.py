"""Immutable values of the refresh_document slice (spec FR-5.3, decision D11).

The slice never touches the filesystem: the caller re-reads and re-parses the file and
hands over the old and the freshly built card tree. Everything here is a pure value so
that a refresh decision can be compared, stored and tested directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from mcwr.domain.models import CardId, CardLayout

SignaturePart = int | None
"""One structural element of :class:`StructureSignature` (a heading level, or ``None``)."""


@dataclass(frozen=True, slots=True)
class StructureSignature:
    """The structure of a card tree, reduced to the criterion of decision D11.

    ``top_cards`` counts the big-section cards (the roots) and ``heading_levels``
    lists the level of every heading card in document order; ``part_count`` counts the
    top-level cards plus the headings, so two signatures can never collide by accident
    (``(1, (2,))`` and ``(2, ())`` describe different trees).
    """

    top_cards: int
    heading_levels: tuple[int, ...]
    part_count: int

    @property
    def parts(self) -> tuple[SignaturePart, ...]:
        """The signature as one comparable sequence: top-level cards first, then levels."""
        return (self.top_cards, *self.heading_levels)


@dataclass(frozen=True, slots=True)
class CardMapping:
    """Result of matching an old card tree against a new one (spec §2.4).

    ``kept`` maps an old card id to the new id that now carries it, ``added`` lists the
    new cards that match no old card and ``removed`` the old cards that match no new
    card. The mapping is a partition: every new card id appears exactly once across
    ``kept.values()`` and ``added``, every old card id exactly once across ``kept`` keys
    and ``removed``. :meth:`__post_init__` enforces that (see also
    :func:`mcwr.application.features.refresh_document.service.match_cards`).
    """

    kept: dict[CardId, CardId]
    added: tuple[CardId, ...]
    removed: tuple[CardId, ...]

    def __post_init__(self) -> None:
        seen_new: set[CardId] = set()
        for old_id, new_id in self.kept.items():
            if new_id in seen_new:
                raise ValueError(f"new card {new_id!r} is claimed twice: {old_id!r} and more")
            seen_new.add(new_id)
        for new_id in self.added:
            if new_id in seen_new:
                raise ValueError(f"new card {new_id!r} is both mapped and added")
            seen_new.add(new_id)
        if len(seen_new) != len(self.kept) + len(self.added):
            raise ValueError("added contains duplicate card ids")

    def summary(self) -> str:
        """One-line human-readable counts, used in the refresh notes."""
        return f"{len(self.kept)} kept, {len(self.added)} added, {len(self.removed)} removed"


@dataclass(frozen=True, slots=True)
class RefreshPlan:
    """What the UI has to apply after a refresh, plus the notes shown to the user.

    ``major`` is the D11 verdict. When it is true ``layouts`` is empty on purpose: the
    user's old geometry is *not* silently reused and the caller rebuilds the board from
    the new tree with :func:`mcwr.application.features.layout_board.service.layout_board`.
    ``mapping`` always describes the full match, so the caller can still report how many
    cards were updated, added and removed.
    """

    major: bool
    layouts: dict[CardId, CardLayout]
    mapping: CardMapping
    warnings: tuple[str, ...] = ()


RESTORED_KEYS: Final[tuple[str, ...]] = (
    "x",
    "y",
    "width",
    "height",
    "z",
    "collapsed",
    "detached",
    "manual_size",
    "scale",
)
"""The :class:`CardLayout` fields a refresh carries over from the old layout."""
