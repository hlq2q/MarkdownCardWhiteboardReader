"""Refresh decision and layout merge: old tree + new tree -> plan (FR-5.3, D11).

The slice is pure: the caller re-reads and re-parses the document (FR-5.2) and passes
both card trees plus the layouts currently on screen. Nothing here touches the disk and
nothing here mutates its inputs.

The decision follows decision D11: a change is *major* when the number of big sections
changes or when the sequence of heading levels changes. Body-text edits and card
additions/removals inside an unchanged heading structure are **not** major (FR-5.4).
"""

from __future__ import annotations

from collections.abc import Mapping

from mcwr.application.features.refresh_document.models import (
    RESTORED_KEYS,
    CardMapping,
    RefreshPlan,
    StructureSignature,
)
from mcwr.domain.enums import CardKind
from mcwr.domain.models import Card, CardId, CardLayout, CardTree

_MAJOR_NOTE = (
    "Structure changed substantially, so the board was rebuilt from the new document; "
    "previous card positions and sizes may differ."
)


def structure_signature(tree: CardTree) -> StructureSignature:
    """Return the D11 structure signature of ``tree``.

    The signature is the number of big sections plus the sequence of heading levels in
    document order. Card kinds, card counts, titles, body text and content hashes are
    deliberately excluded, so a signature compares two documents structurally and stays
    independent of the ``dict`` order of ``tree.cards``.
    """
    levels = [card.level for card in _walk(tree) if card.kind is CardKind.HEADING]
    return StructureSignature(
        big_sections=len(tree.root_ids),
        heading_levels=tuple(level for level in levels if level is not None),
        part_count=len(tree.root_ids) + len(levels),
    )


def is_major_change(old_tree: CardTree, new_tree: CardTree) -> bool:
    """Return whether the refresh from ``old_tree`` to ``new_tree`` is major (D11).

    Major means: the number of big sections changed, or the sequence of heading levels
    changed (a heading added, removed, re-levelled or moved relative to the others).
    Body-text edits, a rewritten paragraph, and card additions or removals inside an
    unchanged heading structure are **not** major: they keep every matched card's
    geometry and only new cards receive a default layout.
    """
    old, new = structure_signature(old_tree), structure_signature(new_tree)
    return old.big_sections != new.big_sections or old.heading_levels != new.heading_levels


def match_cards(old_tree: CardTree, new_tree: CardTree) -> CardMapping:
    """Match old cards to new cards so the user's layout can follow them (FR-5.6).

    Pass 1 takes every exact ``card_id`` (``stable_key``) match, which survives a content
    edit because the id is structural. Pass 2 relocates the remaining old cards by
    ``(kind, content_hash)`` over the whole new tree, which recovers an unchanged card
    whose heading was renamed or whose sibling ordinal shifted. Every new card is claimed
    at most once; a relocation prefers the candidate whose ``heading_path`` is closest
    (then the smallest document-order distance, then the new id for determinism). A big
    section is never a relocation candidate: it is a structural container, and its hash
    would otherwise let it absorb a deleted content card's layout.

    Raises:
        ValueError: the result would not be a partition of both trees (a bug).
    """
    order = _document_order_index(new_tree)
    taken_new = set(new_tree.cards)
    matched_new: set[CardId] = set()
    kept: dict[CardId, CardId] = {}
    remaining: list[CardId] = []

    for old_id in old_tree.ordered_ids():
        if old_id in new_tree.cards:
            kept[old_id] = old_id
            matched_new.add(old_id)
            taken_new.discard(old_id)
        else:
            remaining.append(old_id)

    for old_id, new_id in _plan_relocations(old_tree, new_tree, remaining, order, taken_new):
        kept[old_id] = new_id
        matched_new.add(new_id)

    mapping = CardMapping(
        kept=kept,
        added=tuple(new_id for new_id in order if new_id not in matched_new),
        removed=tuple(old_id for old_id in old_tree.ordered_ids() if old_id not in kept),
    )
    _validate(mapping, old_tree, new_tree)
    return mapping


def merge_layouts(
    old_layouts: Mapping[CardId, CardLayout],
    mapping: CardMapping,
    new_tree: CardTree,
) -> tuple[dict[CardId, CardLayout], tuple[str, ...]]:
    """Merge ``old_layouts`` into new-tree layouts, returning them with notes.

    Kept cards keep their geometry and view state -- position, size, z, ``collapsed``,
    ``detached`` and ``manual_size`` -- re-keyed to the new card id, so a collapsed card
    stays collapsed and a detached card stays detached (FR-5.3, §2.6). New cards get a
    fresh default :class:`CardLayout` (the layout pass decides their position later) and
    are reported; removed cards are reported too, never silently dropped. The notes are
    human-readable English strings meant to be shown to the user.

    This function merges whatever mapping it is given: the major-change guard belongs to
    :func:`plan_refresh`, which returns an empty layout dict in that case.

    Raises:
        ValueError: the mapping does not partition ``new_tree`` (a bug, see
            :func:`match_cards`).
    """
    layouts: dict[CardId, CardLayout] = {
        new_id: _merge_one(old_layouts, old_id, new_id) for old_id, new_id in mapping.kept.items()
    }
    for new_id in mapping.added:
        layouts[new_id] = CardLayout(card_id=new_id)

    notes = _merge_notes(old_layouts, mapping)
    if set(layouts) != set(new_tree.cards):
        raise ValueError(
            "mapping does not partition the new tree: "
            f"layouts={len(layouts)} cards={len(new_tree.cards)}"
        )
    return layouts, notes


def _merge_one(
    old_layouts: Mapping[CardId, CardLayout], old_id: CardId, new_id: CardId
) -> CardLayout:
    """The new layout of one kept card: its old geometry, or a fresh default."""
    old = old_layouts.get(old_id)
    return CardLayout(card_id=new_id) if old is None else _restore_geometry(old, new_id)


def _merge_notes(old_layouts: Mapping[CardId, CardLayout], mapping: CardMapping) -> tuple[str, ...]:
    """Human-readable notes for one merge: new, removed and unpositioned cards."""
    notes: list[str] = []
    if mapping.added:
        notes.append(
            f"{len(mapping.added)} new card(s) placed with a default size; their position "
            "is decided by the layout pass."
        )
    if mapping.removed:
        notes.append(
            f"{len(mapping.removed)} card(s) are no longer in the document and were removed "
            "from the board."
        )
    missing = sum(1 for old_id in mapping.kept if old_id not in old_layouts)
    if missing:
        notes.append(f"{missing} card(s) had no stored position and received a default size.")
    return tuple(notes)


def plan_refresh(
    old_tree: CardTree,
    new_tree: CardTree,
    old_layouts: Mapping[CardId, CardLayout],
) -> RefreshPlan:
    """Decide what a refresh has to apply, and explain it to the user (FR-5.3).

    A major change (D11, see :func:`is_major_change`) yields an **empty** layout dict plus
    a warning naming the reason and a note that the board is rebuilt from the new
    document; the old layout is never silently reused nor silently discarded. Otherwise
    the old geometry is merged by :func:`merge_layouts`.

    The caller is responsible for re-reading and re-parsing the document first (FR-5.2);
    this function only merges.
    """
    mapping = match_cards(old_tree, new_tree)
    if is_major_change(old_tree, new_tree):
        warnings = (*major_change_warnings(old_tree, new_tree), _MAJOR_NOTE)
        return RefreshPlan(major=True, layouts={}, mapping=mapping, warnings=warnings)

    layouts, notes = merge_layouts(old_layouts, mapping, new_tree)
    return RefreshPlan(major=False, layouts=layouts, mapping=mapping, warnings=notes)


def major_change_warnings(old_tree: CardTree, new_tree: CardTree) -> tuple[str, ...]:
    """Name every reason why the refresh counts as major (empty when it is not)."""
    old, new = structure_signature(old_tree), structure_signature(new_tree)
    reasons: list[str] = []
    if old.big_sections != new.big_sections:
        reasons.append(
            f"the number of big sections changed from {old.big_sections} to {new.big_sections}"
        )
    if old.heading_levels != new.heading_levels:
        reasons.append(
            "the sequence of heading levels changed from "
            f"{list(old.heading_levels)} to {list(new.heading_levels)}"
        )
    return tuple(f"Major structure change: {reason}." for reason in reasons)


def _restore_geometry(old: CardLayout, new_id: CardId) -> CardLayout:
    """Copy ``old`` onto a layout re-keyed to ``new_id``, restoring every kept field."""
    layout = CardLayout(card_id=new_id)
    for key in RESTORED_KEYS:
        setattr(layout, key, getattr(old, key))
    return layout


def _walk(tree: CardTree) -> tuple[Card, ...]:
    """The cards of ``tree`` in document order."""
    return tuple(tree.cards[card_id] for card_id in tree.ordered_ids() if card_id in tree.cards)


def _document_order_index(tree: CardTree) -> dict[CardId, int]:
    return {card_id: position for position, card_id in enumerate(tree.ordered_ids())}


def _plan_relocations(
    old_tree: CardTree,
    new_tree: CardTree,
    remaining: list[CardId],
    order: Mapping[CardId, int],
    taken: set[CardId],
) -> tuple[tuple[CardId, CardId], ...]:
    """Second pass: claim each relocatable old card's best free new candidate."""
    candidates: dict[tuple[CardKind, str], list[CardId]] = {}
    for new_id in order:
        card = new_tree.cards[new_id]
        if card.kind is CardKind.BIG_SECTION:
            continue
        if new_id in taken:
            candidates.setdefault((card.kind, card.content_hash), []).append(new_id)

    old_order = _document_order_index(old_tree)
    matched: list[tuple[CardId, CardId]] = []
    for old_id in sorted(remaining, key=lambda card_id: old_order.get(card_id, -1)):
        old_card = old_tree.cards[old_id]
        pool = candidates.get((old_card.kind, old_card.content_hash), [])
        if not pool:
            continue
        best = min(
            pool, key=lambda new_id: _candidate_rank(old_card, new_tree.cards[new_id], order)
        )
        matched.append((old_id, best))
        pool.remove(best)
    return tuple(matched)


def _candidate_rank(old: Card, new: Card, order: Mapping[CardId, int]) -> tuple[int, int, int, str]:
    """Order candidates: closest heading path, then closest document position, then id.

    The heading-path distance counts the names that differ plus the depth difference, so
    a card that stayed under a renamed ancestor beats a card that only shares one name.
    Keying on the new id last keeps the choice independent of the ``dict`` order of
    ``tree.cards``, so the same two documents always match the same way.
    """
    old_path, new_path = set(old.heading_path), set(new.heading_path)
    path_distance = len(old_path ^ new_path) + abs(len(old.heading_path) - len(new.heading_path))
    order_distance = abs(order.get(old.card_id, 0) - order.get(new.card_id, 0))
    return (path_distance, order_distance, len(new_path), new.card_id)


def _validate(mapping: CardMapping, old_tree: CardTree, new_tree: CardTree) -> None:
    """Prove the mapping is a partition of both trees; a failure is a bug, never input."""
    old_ids = set(old_tree.cards)
    new_ids = set(new_tree.cards)
    covered_new = set(mapping.kept.values()) | set(mapping.added)
    if covered_new != new_ids:
        missing = sorted(new_ids - covered_new)
        extra = sorted(covered_new - new_ids)
        raise ValueError(f"mapping does not cover the new tree: missing={missing} extra={extra}")
    covered_old = set(mapping.kept) | set(mapping.removed)
    if covered_old != old_ids:
        missing_old = sorted(old_ids - covered_old)
        extra_old = sorted(covered_old - old_ids)
        raise ValueError(
            f"mapping does not cover the old tree: missing={missing_old} extra={extra_old}"
        )
    if len(covered_new) != len(mapping.kept) + len(mapping.added):
        raise ValueError("a new card is claimed by more than one old card")
    if len(covered_old) != len(mapping.kept) + len(mapping.removed):
        raise ValueError("an old card appears both as kept and as removed")
