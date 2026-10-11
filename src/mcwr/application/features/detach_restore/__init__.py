"""Feature slice: detach a card from its parent, restore it, or restore everything."""

from __future__ import annotations

from mcwr.application.features.detach_restore.models import LayoutChange
from mcwr.application.features.detach_restore.service import (
    can_detach,
    detach_card,
    reclaim_children,
    restore_all,
    restore_card,
    toggle_collapse,
)

__all__ = [
    "LayoutChange",
    "can_detach",
    "detach_card",
    "reclaim_children",
    "restore_all",
    "restore_card",
    "toggle_collapse",
]
