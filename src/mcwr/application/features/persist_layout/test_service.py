"""Tests for the persist_layout use case, using hand-written fakes (no mocks)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from mcwr.application.features.persist_layout.models import RestoredLayout
from mcwr.application.features.persist_layout.ports import LayoutStore
from mcwr.application.features.persist_layout.service import (
    empty_snapshot,
    persist_snapshot,
    restore_snapshot,
)
from mcwr.domain.errors import LayoutCorruptedError
from mcwr.domain.models import (
    SNAPSHOT_SCHEMA_VERSION,
    BoardSnapshot,
    CardLayout,
    DocumentKey,
    WindowState,
)


class FakeStore:
    """Minimal in-memory LayoutStore; the only failure it can be told to raise is D9's."""

    def __init__(
        self,
        snapshot: BoardSnapshot | Exception | None = None,
        window: WindowState | None = None,
    ) -> None:
        self._snapshot = snapshot
        self._window = window
        self.saved: list[tuple[BoardSnapshot, str]] = []
        self.loaded: list[tuple[DocumentKey, str]] = []
        self.saved_windows: list[WindowState] = []

    def load_snapshot(self, document: DocumentKey, *, session: str) -> BoardSnapshot | None:
        self.loaded.append((document, session))
        if isinstance(self._snapshot, Exception):
            raise self._snapshot
        return self._snapshot

    def save_snapshot(self, snapshot: BoardSnapshot, *, session: str) -> None:
        self.saved.append((snapshot, session))
        self._snapshot = snapshot

    def load_window(self, window_uuid: str) -> WindowState | None:
        return self._window

    def save_window(self, state: WindowState) -> None:
        self.saved_windows.append(state)
        self._window = state


def _document(tmp_path: Path, name: str = "doc.md") -> DocumentKey:
    return DocumentKey(
        path=tmp_path / name,
        path_hash="abc123abc123",
        size=42,
        mtime=1234.5,
        content_hash="deadbeefcafe",
    )


def _snapshot(document: DocumentKey, *, window_uuid: str = "window-a") -> BoardSnapshot:
    return BoardSnapshot(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        document=document,
        layouts={"card-1": CardLayout(card_id="card-1", x=10.0, y=20.0, width=300.0, height=200.0)},
        viewport=replace(empty_snapshot(document, window_uuid=window_uuid).viewport, scale=1.5),
        window_uuid=window_uuid,
    )


def test_stored_snapshot_of_this_window_is_returned_untouched(tmp_path: Path) -> None:
    document = _document(tmp_path)
    stored = _snapshot(document)
    restored = restore_snapshot(
        document, store=FakeStore(stored), session="s1", window_uuid="window-a"
    )
    assert restored.snapshot is stored
    assert restored.warnings == ()


def test_snapshot_seeded_from_another_window_is_rebound_to_this_window(tmp_path: Path) -> None:
    document = _document(tmp_path)
    stored = _snapshot(document, window_uuid="window-a")
    restored = restore_snapshot(
        document, store=FakeStore(stored), session="s2", window_uuid="window-b"
    )
    assert restored.snapshot.window_uuid == "window-b"
    assert restored.snapshot.layouts == stored.layouts
    assert restored.snapshot.viewport.scale == 1.5
    assert stored.window_uuid == "window-a"  # the stored board is not mutated


def test_missing_snapshot_degrades_to_an_empty_board_with_a_warning(tmp_path: Path) -> None:
    document = _document(tmp_path)
    restored = restore_snapshot(
        document, store=FakeStore(None), session="fresh", window_uuid="window-a"
    )
    assert restored.snapshot.layouts == {}
    assert restored.snapshot.viewport.scale == 1.0
    assert restored.snapshot.document is document
    assert restored.snapshot.schema_version == SNAPSHOT_SCHEMA_VERSION
    assert restored.snapshot.window_uuid == "window-a"
    assert len(restored.warnings) == 1
    assert "fresh" in restored.warnings[0]


def test_corrupted_snapshot_never_crashes_and_is_reported(tmp_path: Path) -> None:
    document = _document(tmp_path)
    failure = LayoutCorruptedError("boards/abc/s1.json", "schema version 99")
    restored = restore_snapshot(
        document, store=FakeStore(failure), session="s1", window_uuid="window-a"
    )
    assert isinstance(restored, RestoredLayout)
    assert restored.snapshot.layouts == {}
    assert restored.snapshot.schema_version == SNAPSHOT_SCHEMA_VERSION
    assert any("schema version 99" in warning for warning in restored.warnings)


def test_store_receives_exactly_the_requested_session(tmp_path: Path) -> None:
    document = _document(tmp_path)
    store = FakeStore(None)
    restore_snapshot(document, store=store, session="session-9", window_uuid="w")
    assert store.loaded == [(document, "session-9")]


def test_persist_snapshot_goes_through_the_store(tmp_path: Path) -> None:
    document = _document(tmp_path)
    store = FakeStore(None)
    snapshot = _snapshot(document)
    persist_snapshot(snapshot, store=store, session="s1")
    assert store.saved == [(snapshot, "s1")]


def test_fake_store_satisfies_the_port_structurally() -> None:
    """The protocol is structural: an adapter needs no inheritance to be a LayoutStore."""
    store: LayoutStore = FakeStore(None)
    state = WindowState(window_uuid="w1", x=5, y=6, width=800, height=600)
    store.save_window(state)
    assert store.load_window("w1") == state
