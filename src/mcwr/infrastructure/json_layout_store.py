"""Atomic JSON storage of board snapshots and window state (D9, D15, FR-7.4).

Layout for one app-data root::

    boards/<path_hash>/<session>.json     # one snapshot per document and session
    boards/<path_hash>/last_session.json  # {"session": ..., "document_path": ...}
    windows/<window_uuid>.json            # geometry, open documents, active document

A snapshot is written by temp file + ``flush`` + ``fsync`` + ``os.replace``, so a reader
never sees a half-written board and no ``*.tmp`` file survives. A session that has no
snapshot yet starts from a **copy** of the last session's snapshot, which is how a new
window recovers the layout without ever sharing (and thereby overwriting) the file of a
session that is still running (D15).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Final

from mcwr.domain.errors import LayoutCorruptedError
from mcwr.domain.models import SNAPSHOT_SCHEMA_VERSION, BoardSnapshot, DocumentKey, WindowState
from mcwr.infrastructure import _layout_codec as codec
from mcwr.infrastructure._atomic import check_plain_name, write_text_atomic
from mcwr.infrastructure._layout_codec import JsonValue

BOARDS_DIRNAME: Final[str] = "boards"
WINDOWS_DIRNAME: Final[str] = "windows"
LAST_SESSION_FILENAME: Final[str] = "last_session.json"


class JsonLayoutStore:
    """Implements :class:`mcwr.application.features.persist_layout.ports.LayoutStore`."""

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        """The app-data root this store owns; nothing is ever written outside it."""
        return self._root

    # ------------------------------------------------------------------ snapshots

    def load_snapshot(self, document: DocumentKey, *, session: str) -> BoardSnapshot | None:
        """Return the session's snapshot, seeding it from the last session when needed.

        Raises:
            LayoutCorruptedError: the session file exists but is unreadable, invalid,
                carries another schema version or path hash, or has malformed fields.
        """
        check_plain_name(session, "session name")
        path = self._snapshot_path(document, session)
        if path.exists():
            return self._read_snapshot(path, document)
        previous = self._referenced_session(document)
        if previous is None or previous == session:
            return None
        self._adopt(previous, document, session)
        return self._read_snapshot(path, document)

    def save_snapshot(self, snapshot: BoardSnapshot, *, session: str) -> None:
        """Write the snapshot atomically and point ``last_session.json`` at ``session``."""
        check_plain_name(session, "session name")
        path = self._snapshot_path(snapshot.document, session)
        self._write_object(path, codec.snapshot_to_object(snapshot))
        self._write_last_session(snapshot, session)

    # --------------------------------------------------------------------- windows

    def load_window(self, window_uuid: str) -> WindowState | None:
        """Return the stored state of ``window_uuid``, or ``None`` when there is none.

        Raises:
            LayoutCorruptedError: the window file exists but is unreadable or malformed.
        """
        check_plain_name(window_uuid, "window uuid")
        path = self._windows_dir / f"{window_uuid}.json"
        if not path.exists():
            return None
        raw = self._read_json_object(path)
        try:
            return codec.window_from_object(raw)
        except codec.CodecError as exc:
            raise _corrupted(path, exc) from exc

    def save_window(self, state: WindowState) -> None:
        """Write one window state atomically."""
        check_plain_name(state.window_uuid, "window uuid")
        path = self._windows_dir / f"{state.window_uuid}.json"
        self._write_object(path, codec.window_to_object(state))

    # ------------------------------------------------------------------- snapshots

    def _read_snapshot(self, path: Path, document: DocumentKey) -> BoardSnapshot:
        raw = self._read_json_object(path)
        try:
            snapshot = codec.snapshot_from_object(raw)
        except codec.CodecError as exc:
            raise _corrupted(path, exc) from exc
        if snapshot.schema_version != SNAPSHOT_SCHEMA_VERSION:
            reason = (
                f"schema version {snapshot.schema_version} does not match {SNAPSHOT_SCHEMA_VERSION}"
            )
            raise LayoutCorruptedError(str(path), reason)
        if snapshot.document.path_hash != document.path_hash:
            reason = (
                f"snapshot belongs to path hash {snapshot.document.path_hash!r}, "
                f"not {document.path_hash!r}"
            )
            raise LayoutCorruptedError(str(path), reason)
        return snapshot

    def _adopt(self, previous: str, document: DocumentKey, session: str) -> None:
        """Copy the last session's snapshot into ``session``; the original is left alone."""
        source = self._snapshot_path(document, previous)
        if not source.exists():
            return
        seeded = self._read_snapshot(source, document)
        self.save_snapshot(seeded, session=session)

    def _referenced_session(self, document: DocumentKey) -> str | None:
        """Return the session named by ``last_session.json`` for this document, if any."""
        pointer = self._boards_dir / document.path_hash / LAST_SESSION_FILENAME
        if not pointer.exists():
            return None
        try:
            raw = self._read_json_object(pointer)
            named = codec.string_value(codec.field_value(raw, "session"))
            owner = codec.string_value(codec.field_value(raw, "document_path"))
        except (codec.CodecError, LayoutCorruptedError):
            return None
        # A stale pointer (the document moved) must not seed this document's board.
        if _same_document(Path(owner), document.path):
            return named
        return None

    def _write_last_session(self, snapshot: BoardSnapshot, session: str) -> None:
        payload: dict[str, JsonValue] = {
            "session": session,
            "document_path": str(snapshot.document.path),
        }
        self._write_object(
            self._boards_dir / snapshot.document.path_hash / LAST_SESSION_FILENAME, payload
        )

    # ------------------------------------------------------------------------ files

    def _snapshot_path(self, document: DocumentKey, session: str) -> Path:
        return self._boards_dir / document.path_hash / f"{session}.json"

    @property
    def _boards_dir(self) -> Path:
        return self._root / BOARDS_DIRNAME

    @property
    def _windows_dir(self) -> Path:
        return self._root / WINDOWS_DIRNAME

    def _read_json_object(self, path: Path) -> dict[str, JsonValue]:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise LayoutCorruptedError(str(path), f"cannot read ({exc})") from exc
        try:
            return codec._object(codec._decode(text))
        except codec.CodecError as exc:
            raise _corrupted(path, exc) from exc

    def _write_object(self, path: Path, payload: dict[str, JsonValue]) -> None:
        text = json.dumps(payload, ensure_ascii=False, indent=codec.INDENT) + "\n"
        write_text_atomic(path, text)


# ------------------------------------------------------------------------- helpers


def _corrupted(path: Path, exc: codec.CodecError) -> LayoutCorruptedError:
    return LayoutCorruptedError(str(path), exc.reason)


def _same_document(stored: Path, opened: Path) -> bool:
    """Compare paths case-insensitively, tolerating a relative path in a stored key."""
    left = os.path.normcase(str(stored.resolve()))
    right = os.path.normcase(str(opened.resolve()))
    return left == right
