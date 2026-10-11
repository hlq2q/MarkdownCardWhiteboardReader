"""Round-trip fidelity of the on-disk layout format: every field of every model."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcwr.domain.errors import LayoutCorruptedError
from mcwr.domain.models import SNAPSHOT_SCHEMA_VERSION, CardLayout, WindowState
from mcwr.infrastructure.json_layout_store import JsonLayoutStore
from mcwr.infrastructure.test_layout_support import document, read_json, session_file, snapshot


def test_snapshot_round_trip_preserves_every_field(tmp_path: Path) -> None:
    owner = document(tmp_path)
    board = snapshot(owner)
    store = JsonLayoutStore(tmp_path / "root")
    store.save_snapshot(board, session="s1")

    loaded = store.load_snapshot(owner, session="s1")

    assert loaded is not None
    assert loaded.schema_version == SNAPSHOT_SCHEMA_VERSION
    assert loaded.window_uuid == "window-a"
    assert loaded.document == owner  # Path, both hashes, size and mtime all survive
    assert loaded.viewport == board.viewport
    assert set(loaded.layouts) == {"card-1", "card-2"}
    assert loaded.layouts["card-1"] == board.layouts["card-1"]
    assert loaded.layouts["card-2"] == CardLayout(card_id="card-2")


def test_document_path_is_stored_as_text_and_read_back_as_a_path(tmp_path: Path) -> None:
    owner = document(tmp_path)
    store = JsonLayoutStore(tmp_path / "root")
    store.save_snapshot(snapshot(owner), session="s1")

    payload = read_json(session_file(tmp_path / "root", owner, "s1"))
    stored = payload["document"]
    assert isinstance(stored, dict)
    assert stored["path"] == str(owner.path)
    assert isinstance(stored["path"], str)

    loaded = store.load_snapshot(owner, session="s1")
    assert loaded is not None
    assert isinstance(loaded.document.path, Path)


def test_active_document_may_be_missing_from_a_window_file(tmp_path: Path) -> None:
    """``active_document: null`` is the "no document open" state, not a corruption."""
    root = tmp_path / "root"
    store = JsonLayoutStore(root)
    store.save_window(WindowState(window_uuid="w1", open_documents=()))
    path = root / "windows" / "w1.json"
    payload = read_json(path)
    payload["active_document"] = None
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = store.load_window("w1")
    assert loaded is not None
    assert loaded.active_document is None
    assert loaded.open_documents == ()


def test_window_round_trip(tmp_path: Path) -> None:
    store = JsonLayoutStore(tmp_path / "root")
    state = WindowState(
        window_uuid="window-1",
        x=11,
        y=22,
        width=1600,
        height=900,
        maximized=True,
        open_documents=("a.md", "b.md"),
        active_document="b.md",
    )
    store.save_window(state)

    loaded = store.load_window("window-1")
    assert loaded == state
    assert loaded is not None
    assert loaded.open_documents == ("a.md", "b.md")
    assert loaded.active_document == "b.md"


def test_unknown_window_returns_none(tmp_path: Path) -> None:
    store = JsonLayoutStore(tmp_path / "root")
    assert store.load_window("never-seen") is None


def test_corrupt_window_file_raises_layout_corrupted(tmp_path: Path) -> None:
    root = tmp_path / "root"
    store = JsonLayoutStore(root)
    store.save_window(WindowState(window_uuid="window-1"))
    path = root / "windows" / "window-1.json"
    payload = read_json(path)
    payload["width"] = "wide"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(LayoutCorruptedError) as caught:
        store.load_window("window-1")
    assert caught.value.path == str(path)
    assert "expected an integer" in caught.value.reason


def test_layout_key_and_card_id_must_agree(tmp_path: Path) -> None:
    owner = document(tmp_path)
    root = tmp_path / "root"
    store = JsonLayoutStore(root)
    store.save_snapshot(snapshot(owner), session="s1")
    path = session_file(root, owner, "s1")
    payload = read_json(path)
    layouts = payload["layouts"]
    assert isinstance(layouts, dict)
    layouts["card-1"] = {"card_id": "someone-else", "x": 1.0, "y": 1.0, "width": 1.0,
                         "height": 1.0, "z": 0, "collapsed": False, "detached": False,
                         "manual_size": False}
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(LayoutCorruptedError) as caught:
        store.load_snapshot(owner, session="s1")
    assert "card id mismatch" in caught.value.reason
