"""Card identity and content fingerprinting (spec §2.4, decision D4).

Two keys, deliberately kept apart:

``stable_key`` (used as ``CardId``)
    Structural only: document path hash, heading path, card kind, sibling ordinal and
    the occurrence index of that heading path. Editing the *content* of a card never
    changes it, which is what lets a refresh keep the user's layout (FR-5.3).

``content_hash``
    Normalised-text fingerprint. Used to detect that a card's content changed and to
    invalidate render caches. Never part of the identity.

Known limitation (documented in the spec, handled by the refresh matcher):
inserting a sibling *above* a card shifts its ordinal, so its ``stable_key`` changes.
``refresh_document`` therefore falls back to ``(kind, content_hash)`` relocation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

from mcwr.domain.enums import CardKind

_DEFAULT_LENGTH: Final[int] = 12


def normalize_text(text: str) -> str:
    """Collapse all whitespace runs to single spaces and strip the ends."""
    return " ".join(text.replace("\r\n", "\n").replace("\r", "\n").split())


def content_hash(text: str, *, length: int = _DEFAULT_LENGTH) -> str:
    """Return a stable fingerprint of the normalised text."""
    return hashlib.sha1(normalize_text(text).encode("utf-8")).hexdigest()[:length]


def document_path_hash(path: Path, *, length: int = _DEFAULT_LENGTH) -> str:
    """Return a case-insensitive hash of the absolute path (snapshot file naming)."""
    key = str(path.resolve()).replace("\\", "/").casefold()
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:length]


def stable_key(
    *,
    path_hash: str,
    heading_path: tuple[str, ...],
    card_kind: CardKind,
    ordinal_in_parent: int,
    occurrence: int,
    length: int = _DEFAULT_LENGTH,
) -> str:
    """Build the structural card identity (``str``), stable across content edits.

    The payload is JSON so that no heading text can collide with the encoding itself
    (a plain separator would let ``("a\\x1fb",)`` equal ``("a", "b")``).
    """
    payload = json.dumps(
        [path_hash, list(heading_path), str(card_kind), ordinal_in_parent, occurrence],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return digest[:length]
