"""Shared fixtures for the layout-store tests: documents, snapshots and a tiny file tree.

Not a test module itself (the name does not start with ``test_``), so pytest never
collects it — it only keeps the two store test modules focused on behaviour.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from mcwr.domain.ids import document_path_hash
from mcwr.domain.models import (
    SNAPSHOT_SCHEMA_VERSION,
    BoardSnapshot,
    CardLayout,
    DocumentKey,
    Viewport,
    WindowState,
)
from mcwr.infrastructure._layout_codec import JsonValue


def document(tmp_path: Path, name: str = "doc.md") -> DocumentKey:
    """A document key for ``tmp_path/name``, hashed the way production hashes it."""
    path = tmp_path / name
    return DocumentKey(
        path=path,
        path_hash=document_path_hash(path),
        size=42,
        mtime=1234.5,
        content_hash="deadbeefcafe",
    )


def snapshot(owner: DocumentKey, *, window_uuid: str = "window-a") -> BoardSnapshot:
    """A snapshot that differs from the defaults in every single field."""
    return BoardSnapshot(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        document=owner,
        layouts={
            "card-1": CardLayout(
                card_id="card-1",
                x=1.5,
                y=-2.25,
                width=320.5,
                height=240.0,
                z=3,
                collapsed=True,
                detached=True,
                manual_size=True,
            ),
            "card-2": CardLayout(card_id="card-2"),
        },
        viewport=Viewport(scale=2.5, pan_x=-40.5, pan_y=15.25, fitted_once=True),
        window_uuid=window_uuid,
    )


def window() -> WindowState:
    """A window state that differs from the defaults in every field."""
    return WindowState(
        window_uuid="window-1",
        x=11,
        y=22,
        width=1600,
        height=900,
        maximized=True,
        open_documents=("a.md", "b.md"),
        active_document="b.md",
    )


def tree(root: Path) -> set[str]:
    """Every entry under ``root`` — used to prove nothing lingers and nothing escapes."""
    return {path.relative_to(root).as_posix() for path in root.rglob("*")}


def session_file(root: Path, owner: DocumentKey, session: str) -> Path:
    """The file a session's snapshot must live in."""
    return root / "boards" / owner.path_hash / f"{session}.json"


def pointer_file(root: Path, owner: DocumentKey) -> Path:
    """The ``last_session.json`` file of one document."""
    return root / "boards" / owner.path_hash / "last_session.json"


def read_json(path: Path) -> dict[str, JsonValue]:
    """The raw JSON object on disk, so a test can damage exactly one field."""
    return as_object(cast(JsonValue, json.loads(path.read_text(encoding="utf-8"))))


def as_object(value: JsonValue) -> dict[str, JsonValue]:
    """Narrow a decoded value to a JSON object for spreading into a damaged payload."""
    assert isinstance(value, dict)
    return value
