"""Ports of the persist_layout slice (implemented by infrastructure adapters)."""

from __future__ import annotations

from typing import Protocol

from mcwr.domain.models import BoardSnapshot, DocumentKey, WindowState


class LayoutStore(Protocol):
    """Reads and writes board snapshots and window state. Structural, not inherited."""

    def load_snapshot(self, document: DocumentKey, *, session: str) -> BoardSnapshot | None:
        """Return the snapshot stored for ``document`` in ``session``, or ``None``.

        Raises:
            LayoutCorruptedError: the stored snapshot exists but is unreadable,
                carries another schema version or path hash, or has malformed fields.
        """
        ...

    def save_snapshot(self, snapshot: BoardSnapshot, *, session: str) -> None:
        """Persist ``snapshot`` for ``session`` and remember it as the last session."""
        ...

    def load_window(self, window_uuid: str) -> WindowState | None:
        """Return the stored state of ``window_uuid``, or ``None`` when it is unknown.

        Raises:
            LayoutCorruptedError: the stored window file is unreadable or malformed.
        """
        ...

    def save_window(self, state: WindowState) -> None:
        """Persist the state of one window."""
        ...
