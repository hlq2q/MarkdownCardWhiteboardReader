"""Tests for the atomic JSON layout store (D9, D15, FR-7.4).

Round-trip fidelity of every model field, and the window-file format, live in
``test_layout_roundtrip.py``; this module covers the store's file semantics.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcwr.domain.errors import LayoutCorruptedError
from mcwr.domain.models import SNAPSHOT_SCHEMA_VERSION
from mcwr.infrastructure.json_layout_store import LAST_SESSION_FILENAME, JsonLayoutStore
from mcwr.infrastructure.test_layout_support import (
    as_object,
    document,
    pointer_file,
    read_json,
    session_file,
    snapshot,
    tree,
    window,
)


def test_missing_session_returns_none(tmp_path: Path) -> None:
    store = JsonLayoutStore(tmp_path / "root")
    assert store.load_snapshot(document(tmp_path), session="never-saved") is None


def test_save_snapshot_updates_the_last_session_pointer(tmp_path: Path) -> None:
    owner = document(tmp_path)
    root = tmp_path / "root"
    store = JsonLayoutStore(root)
    store.save_snapshot(snapshot(owner), session="s1")

    assert read_json(pointer_file(root, owner)) == {
        "session": "s1",
        "document_path": str(owner.path),
    }

    store.save_snapshot(snapshot(owner), session="s2")
    assert read_json(pointer_file(root, owner))["session"] == "s2"


def test_corrupt_json_raises_layout_corrupted(tmp_path: Path) -> None:
    owner = document(tmp_path)
    root = tmp_path / "root"
    store = JsonLayoutStore(root)
    store.save_snapshot(snapshot(owner), session="s1")
    path = session_file(root, owner, "s1")
    path.write_text("{ this is not json", encoding="utf-8")

    with pytest.raises(LayoutCorruptedError) as caught:
        store.load_snapshot(owner, session="s1")
    assert caught.value.path == str(path)
    assert "invalid JSON" in caught.value.reason


def test_schema_version_mismatch_raises(tmp_path: Path) -> None:
    owner = document(tmp_path)
    root = tmp_path / "root"
    store = JsonLayoutStore(root)
    store.save_snapshot(snapshot(owner), session="s1")
    path = session_file(root, owner, "s1")
    payload = read_json(path)
    payload["schema_version"] = SNAPSHOT_SCHEMA_VERSION + 1
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(LayoutCorruptedError) as caught:
        store.load_snapshot(owner, session="s1")
    assert "schema version" in caught.value.reason


def test_missing_schema_version_raises(tmp_path: Path) -> None:
    owner = document(tmp_path)
    root = tmp_path / "root"
    store = JsonLayoutStore(root)
    store.save_snapshot(snapshot(owner), session="s1")
    path = session_file(root, owner, "s1")
    payload = read_json(path)
    del payload["schema_version"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(LayoutCorruptedError) as caught:
        store.load_snapshot(owner, session="s1")
    assert "schema_version" in caught.value.reason


def test_wrong_document_path_hash_raises(tmp_path: Path) -> None:
    owner = document(tmp_path)
    root = tmp_path / "root"
    store = JsonLayoutStore(root)
    store.save_snapshot(snapshot(owner), session="s1")
    path = session_file(root, owner, "s1")
    payload = read_json(path)
    payload["document"] = {**as_object(payload["document"]), "path_hash": "other-hash"}
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(LayoutCorruptedError) as caught:
        store.load_snapshot(owner, session="s1")
    assert "path hash" in caught.value.reason


def test_malformed_field_type_raises(tmp_path: Path) -> None:
    owner = document(tmp_path)
    root = tmp_path / "root"
    store = JsonLayoutStore(root)
    store.save_snapshot(snapshot(owner), session="s1")
    path = session_file(root, owner, "s1")
    payload = read_json(path)
    payload["viewport"] = {**as_object(payload["viewport"]), "scale": "big"}
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(LayoutCorruptedError) as caught:
        store.load_snapshot(owner, session="s1")
    assert "expected a number" in caught.value.reason


def test_new_window_seeds_from_the_last_session_without_touching_it(tmp_path: Path) -> None:
    owner = document(tmp_path)
    root = tmp_path / "root"
    store = JsonLayoutStore(root)
    store.save_snapshot(snapshot(owner), session="session-old")
    original = session_file(root, owner, "session-old").read_bytes()

    seeded = store.load_snapshot(owner, session="session-new")

    assert seeded is not None
    assert seeded.layouts["card-1"].x == 1.5
    assert seeded.viewport.scale == 2.5
    assert session_file(root, owner, "session-old").read_bytes() == original  # copy, not move
    assert session_file(root, owner, "session-new").exists()
    assert read_json(pointer_file(root, owner))["session"] == "session-new"


def test_a_new_session_is_not_seeded_from_another_document(tmp_path: Path) -> None:
    store = JsonLayoutStore(tmp_path / "root")
    store.save_snapshot(snapshot(document(tmp_path, "first.md")), session="session-old")

    assert store.load_snapshot(document(tmp_path, "second.md"), session="session-new") is None


def test_seeded_session_is_then_independent_of_the_original(tmp_path: Path) -> None:
    owner = document(tmp_path)
    store = JsonLayoutStore(tmp_path / "root")
    store.save_snapshot(snapshot(owner), session="session-old")
    seeded = store.load_snapshot(owner, session="session-new")
    assert seeded is not None
    seeded.layouts["card-1"].x = 99.0
    store.save_snapshot(seeded, session="session-new")

    reloaded = store.load_snapshot(owner, session="session-new")
    older = store.load_snapshot(owner, session="session-old")
    assert reloaded is not None
    assert older is not None
    assert reloaded.layouts["card-1"].x == 99.0
    assert older.layouts["card-1"].x == 1.5


def test_atomic_write_leaves_no_temp_files_and_only_expected_paths(tmp_path: Path) -> None:
    owner = document(tmp_path)
    root = tmp_path / "root"
    store = JsonLayoutStore(root)
    store.save_snapshot(snapshot(owner), session="s1")
    store.save_window(window())
    store.load_snapshot(owner, session="s2")  # the seeding path writes too

    assert not list(root.rglob("*.tmp"))
    assert tree(root) <= {
        "boards",
        f"boards/{owner.path_hash}",
        f"boards/{owner.path_hash}/s1.json",
        f"boards/{owner.path_hash}/s2.json",
        f"boards/{owner.path_hash}/{LAST_SESSION_FILENAME}",
        "windows",
        "windows/window-1.json",
    }


def test_store_writes_nothing_outside_its_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    owner = document(tmp_path)
    store = JsonLayoutStore(root)
    store.save_snapshot(snapshot(owner), session="s1")
    store.save_window(window())
    store.load_snapshot(owner, session="s2")

    beside_the_document = [
        path for path in tmp_path.rglob("*") if path.is_file() and root not in path.parents
    ]
    assert beside_the_document == []  # layout never lands next to the Markdown file
    assert list(root.rglob("*.json"))  # ... and it did land inside the store root


def test_a_failed_write_leaves_no_temp_file_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = document(tmp_path)
    root = tmp_path / "root"
    store = JsonLayoutStore(root)
    store.save_snapshot(snapshot(owner), session="s1")
    before = tree(root)

    def exploding_replace(self: Path, target: Path, /) -> Path:
        del self, target  # a stand-in for Path.replace: it only has to fail
        raise OSError("disk gave up")

    monkeypatch.setattr(Path, "replace", exploding_replace)
    with pytest.raises(OSError, match="disk gave up"):
        store.save_snapshot(snapshot(owner), session="s2")

    assert tree(root) == before  # the half-written temp file is gone again
    assert not list(root.rglob("*.tmp"))


def test_session_name_may_not_escape_the_root(tmp_path: Path) -> None:
    store = JsonLayoutStore(tmp_path / "root")
    owner = document(tmp_path)
    with pytest.raises(ValueError, match="session"):
        store.load_snapshot(owner, session="../escape")
    with pytest.raises(ValueError, match="session"):
        store.save_snapshot(snapshot(owner), session="a/b")
    assert not (tmp_path / "escape.json").exists()
