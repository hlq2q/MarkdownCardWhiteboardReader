"""Use case: restore and persist the layout of one document (D9, D15, FR-7.4)."""

from __future__ import annotations

from dataclasses import replace

from mcwr.application.features.persist_layout.models import RestoredLayout
from mcwr.application.features.persist_layout.ports import LayoutStore
from mcwr.domain.errors import LayoutCorruptedError
from mcwr.domain.models import SNAPSHOT_SCHEMA_VERSION, BoardSnapshot, DocumentKey, Viewport


def empty_snapshot(document: DocumentKey, *, window_uuid: str) -> BoardSnapshot:
    """Return the board a document starts with when nothing can be restored."""
    return BoardSnapshot(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        document=document,
        layouts={},
        viewport=Viewport(),
        window_uuid=window_uuid,
    )


def restore_snapshot(
    document: DocumentKey,
    *,
    store: LayoutStore,
    session: str,
    window_uuid: str,
) -> RestoredLayout:
    """Return the snapshot to open ``document`` with, never failing on a bad file.

    A usable stored snapshot is returned as it is, except for its ``window_uuid``: a
    snapshot the store seeded from the last session carries *that* session's window, and
    adopting it keeps the board bound to the window actually showing it (D15: layout is
    never shared between windows). When nothing can be restored the board starts empty —
    a first open, or a store reporting ``LayoutCorruptedError``, which is degraded into an
    empty board plus a warning rather than raised (FR-7.4).
    """
    try:
        stored = store.load_snapshot(document, session=session)
    except LayoutCorruptedError as exc:
        reason = f"stored layout for this document is unusable ({exc.reason}); layout rebuilt"
        return RestoredLayout(
            snapshot=empty_snapshot(document, window_uuid=window_uuid),
            warnings=(reason,),
        )

    if stored is None:
        warning = f"no stored layout for session {session!r}; layout rebuilt from the document"
        return RestoredLayout(
            snapshot=empty_snapshot(document, window_uuid=window_uuid),
            warnings=(warning,),
        )

    if stored.window_uuid != window_uuid:
        return RestoredLayout(snapshot=replace(stored, window_uuid=window_uuid))
    return RestoredLayout(snapshot=stored)


def persist_snapshot(snapshot: BoardSnapshot, *, store: LayoutStore, session: str) -> None:
    """Save ``snapshot`` through the store, so callers never touch the adapter directly."""
    store.save_snapshot(snapshot, session=session)
