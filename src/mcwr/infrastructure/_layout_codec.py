"""JSON <-> domain-model conversion for the layout store (no pickle, no third party).

Kept apart from :mod:`mcwr.infrastructure.json_layout_store` so that file stays small:
this module knows the on-disk *shape* of a snapshot, the store knows the *files*.
Every reader here is strict — a missing key or a wrongly typed field raises
:class:`CodecError`, which the store turns into ``LayoutCorruptedError``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final, cast

from mcwr.domain.models import (
    BoardSnapshot,
    CardLayout,
    DocumentKey,
    Viewport,
    WindowState,
)

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
"""The recursive subset of JSON a snapshot may decode to."""

INDENT: Final[int] = 2
"""Readable, diffable files; the loader does not depend on the layout."""


class CodecError(ValueError):
    """The decoded JSON does not match the expected snapshot or window shape."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ----------------------------------------------------------------------------- writing


def snapshot_to_json(snapshot: BoardSnapshot) -> str:
    """Serialise a snapshot, preserving every field of the domain models."""
    return json.dumps(snapshot_to_object(snapshot), ensure_ascii=False, indent=INDENT)


def snapshot_to_object(snapshot: BoardSnapshot) -> dict[str, JsonValue]:
    """Build the JSON object of a snapshot (the store adds the file-level concerns)."""
    layouts: dict[str, JsonValue] = {
        card_id: layout_to_object(layout) for card_id, layout in snapshot.layouts.items()
    }
    return {
        "schema_version": snapshot.schema_version,
        "document": document_to_object(snapshot.document),
        "layouts": layouts,
        "viewport": viewport_to_object(snapshot.viewport),
        "window_uuid": snapshot.window_uuid,
    }


def window_to_json(state: WindowState) -> str:
    """Serialise one window state."""
    return json.dumps(window_to_object(state), ensure_ascii=False, indent=INDENT)


def window_to_object(state: WindowState) -> dict[str, JsonValue]:
    """Build the JSON object of one window state."""
    return {
        "window_uuid": state.window_uuid,
        "x": state.x,
        "y": state.y,
        "width": state.width,
        "height": state.height,
        "maximized": state.maximized,
        "open_documents": list(state.open_documents),
        "active_document": state.active_document,
    }


def document_to_object(document: DocumentKey) -> dict[str, JsonValue]:
    """Serialise the document key; ``path`` goes out as ``str``."""
    return {
        "path": str(document.path),
        "path_hash": document.path_hash,
        "size": document.size,
        "mtime": document.mtime,
        "content_hash": document.content_hash,
    }


def layout_to_object(layout: CardLayout) -> dict[str, JsonValue]:
    """Serialise one card layout (all eight fields, geometry included)."""
    return {
        "card_id": layout.card_id,
        "x": layout.x,
        "y": layout.y,
        "width": layout.width,
        "height": layout.height,
        "z": layout.z,
        "collapsed": layout.collapsed,
        "detached": layout.detached,
        "manual_size": layout.manual_size,
    }


def viewport_to_object(viewport: Viewport) -> dict[str, JsonValue]:
    """Serialise the canvas transform."""
    return {
        "scale": viewport.scale,
        "pan_x": viewport.pan_x,
        "pan_y": viewport.pan_y,
        "fitted_once": viewport.fitted_once,
    }


# ----------------------------------------------------------------------------- reading


def snapshot_from_json(text: str) -> BoardSnapshot:
    """Parse snapshot JSON, rejecting anything that is not the expected shape."""
    return snapshot_from_object(_object(_decode(text)))


def window_from_json(text: str) -> WindowState:
    """Parse window-state JSON, rejecting anything that is not the expected shape."""
    return window_from_object(_object(_decode(text)))


def snapshot_from_object(raw: dict[str, JsonValue]) -> BoardSnapshot:
    """Build a snapshot from an already decoded JSON object."""
    layouts_raw = _object(field_value(raw, "layouts"))
    layouts: dict[str, CardLayout] = {}
    for card_id, layout_raw in layouts_raw.items():
        layouts[card_id] = layout_from_object(card_id, _object(layout_raw))
    return BoardSnapshot(
        schema_version=_int(field_value(raw, "schema_version")),
        document=document_from_object(_object(field_value(raw, "document"))),
        layouts=layouts,
        viewport=viewport_from_object(_object(field_value(raw, "viewport"))),
        window_uuid=string_value(field_value(raw, "window_uuid")),
    )


def window_from_object(raw: dict[str, JsonValue]) -> WindowState:
    """Build a window state from an already decoded JSON object."""
    open_documents = field_value(raw, "open_documents")
    if not isinstance(open_documents, list):
        raise CodecError("open_documents must be a list")
    return WindowState(
        window_uuid=string_value(field_value(raw, "window_uuid")),
        x=_int(field_value(raw, "x")),
        y=_int(field_value(raw, "y")),
        width=_int(field_value(raw, "width")),
        height=_int(field_value(raw, "height")),
        maximized=_bool(field_value(raw, "maximized")),
        open_documents=tuple(string_value(item) for item in open_documents),
        active_document=_opt_str(field_value(raw, "active_document")),
    )


def document_from_object(raw: dict[str, JsonValue]) -> DocumentKey:
    """Rebuild the document key; ``path`` comes back through ``Path(...)``."""
    return DocumentKey(
        path=Path(string_value(field_value(raw, "path"))),
        path_hash=string_value(field_value(raw, "path_hash")),
        size=_int(field_value(raw, "size")),
        mtime=_float(field_value(raw, "mtime")),
        content_hash=string_value(field_value(raw, "content_hash")),
    )


def layout_from_object(card_id: str, raw: dict[str, JsonValue]) -> CardLayout:
    """Rebuild one card layout, trusting ``card_id`` (the key) over the payload."""
    stored_id = string_value(field_value(raw, "card_id"))
    if stored_id != card_id:
        raise CodecError(f"card id mismatch: layout key {card_id!r} holds {stored_id!r}")
    return CardLayout(
        card_id=card_id,
        x=_float(field_value(raw, "x")),
        y=_float(field_value(raw, "y")),
        width=_float(field_value(raw, "width")),
        height=_float(field_value(raw, "height")),
        z=_int(field_value(raw, "z")),
        collapsed=_bool(field_value(raw, "collapsed")),
        detached=_bool(field_value(raw, "detached")),
        manual_size=_bool(field_value(raw, "manual_size")),
    )


def viewport_from_object(raw: dict[str, JsonValue]) -> Viewport:
    """Rebuild the canvas transform."""
    return Viewport(
        scale=_float(field_value(raw, "scale")),
        pan_x=_float(field_value(raw, "pan_x")),
        pan_y=_float(field_value(raw, "pan_y")),
        fitted_once=_bool(field_value(raw, "fitted_once")),
    )


# ------------------------------------------------------------------------ primitives
# ``field_value`` / ``string_value`` are public because the store reads the small
# ``last_session.json`` pointer with them; every other helper stays private.


def field_value(raw: dict[str, JsonValue], name: str) -> JsonValue:
    """Return field ``name`` of a decoded object, or raise if it is absent."""
    if name not in raw:
        raise CodecError(f"missing field {name!r}")
    return raw[name]


def string_value(value: JsonValue) -> str:
    """Return a JSON string, or raise if the value is anything else."""
    if not isinstance(value, str):
        raise CodecError(f"expected a string, found {_kind(value)}")
    return value


def _decode(text: str) -> JsonValue:
    try:
        return cast(JsonValue, json.loads(text))
    except json.JSONDecodeError as exc:
        raise CodecError(f"invalid JSON ({exc.msg})") from exc


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise CodecError(f"expected a JSON object, found {_kind(value)}")
    return value


def _kind(value: JsonValue) -> str:
    return "null" if value is None else type(value).__name__


def _opt_str(value: JsonValue) -> str | None:
    return None if value is None else string_value(value)


def _int(value: JsonValue) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CodecError(f"expected an integer, found {_kind(value)}")
    return value


def _float(value: JsonValue) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CodecError(f"expected a number, found {_kind(value)}")
    return float(value)


def _bool(value: JsonValue) -> bool:
    if not isinstance(value, bool):
        raise CodecError(f"expected a boolean, found {_kind(value)}")
    return value
