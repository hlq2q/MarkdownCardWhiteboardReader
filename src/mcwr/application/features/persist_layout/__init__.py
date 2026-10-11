"""Feature slice: restore and persist board layout and window state (D9, D15)."""

from __future__ import annotations

from mcwr.application.features.persist_layout.models import RestoredLayout
from mcwr.application.features.persist_layout.ports import LayoutStore
from mcwr.application.features.persist_layout.service import (
    empty_snapshot,
    persist_snapshot,
    restore_snapshot,
)

__all__ = [
    "LayoutStore",
    "RestoredLayout",
    "empty_snapshot",
    "persist_snapshot",
    "restore_snapshot",
]
