"""The TOC card's entries and the click-to-card mapping (FR-2.4, decision D-025).

The author's ``[TOC]`` marker becomes a list of clickable lines here, and the *same* mapping
resolves a click back to a card — one source for "what the line says" and "where it goes",
so the two can never disagree.

The user's answers (2026-10-12) fix the two open points: entries are generated **only** where
``[TOC]``/``[[TOC]]`` is written (no automatic TOC on every document), and **all** heading
levels H1–H6 are listed.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from typing import Final

from mcwr.application.features.build_toc.models import TocEntry
from mcwr.domain.enums import CardKind
from mcwr.domain.models import CardId, CardTree

MIN_LEVEL: Final[int] = 1
MAX_LEVEL: Final[int] = 6
EMPTY_TOC_TEXT: Final[str] = "(no headings in this document)"
"""Body of a TOC card in a document that has no headings at all."""


def slugify(text: str) -> str:
    """A stable anchor for a heading title.

    Lower-cased and normalised, punctuation dropped, whitespace turned into single hyphens;
    CJK characters survive because they count as alphanumeric. An empty result becomes
    ``"section"`` so every heading stays addressable.
    """
    folded = unicodedata.normalize("NFKC", text).casefold()
    out: list[str] = []
    for char in folded:
        if char.isspace():
            out.append("-")
        elif char.isalnum() or char in "-_":
            out.append(char)
    slug = "".join(out).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "section"


def build_toc(tree: CardTree) -> tuple[TocEntry, ...]:
    """One entry per heading card, in document order, with unique anchors.

    Duplicate titles get ``-1``, ``-2``… appended (the shape GitHub uses), so two sections
    with the same title stay separately addressable.
    """
    entries: list[TocEntry] = []
    seen: dict[str, int] = {}
    for card_id in tree.ordered_ids():
        card = tree.cards[card_id]
        if card.kind is not CardKind.HEADING:
            continue
        level = card.level if card.level is not None and 1 <= card.level <= MAX_LEVEL else 1
        base = slugify(card.title)
        count = seen.get(base, 0)
        seen[base] = count + 1
        anchor = base if count == 0 else f"{base}-{count}"
        entries.append(TocEntry(card_id=card_id, label=card.title, anchor=anchor, level=level))
    return tuple(entries)


def resolve_anchor(entries: Sequence[TocEntry], anchor: str) -> CardId | None:
    """The card an anchor points at, or ``None`` when nothing matches."""
    wanted = anchor.strip().lstrip("#")
    if not wanted:
        return None
    for entry in entries:
        if entry.anchor == wanted:
            return entry.card_id
    return None


def toc_markdown(entries: Sequence[TocEntry]) -> str:
    """The TOC card's body: one Markdown link per entry, indented by heading level.

    Markdown (rather than hand-drawn text) is what makes the lines real links inside the
    card's ``QTextDocument``, so a click can be resolved with ``anchorAt``.
    """
    if not entries:
        return EMPTY_TOC_TEXT
    top = min(entry.level for entry in entries)
    lines = [f"{'  ' * (entry.level - top)}- [{entry.label}](#{entry.anchor})" for entry in entries]
    return "\n".join(lines)
