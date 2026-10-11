"""Board session: owns one open document plus its layout state for one window (FR-6.2).

This is the MVVM boundary: Qt signals outward, application use cases inward. It never
touches widgets, and it is the only place that knows about persistence, so the window
class stays a thin binding layer.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from mcwr import container
from mcwr.application.features.detach_restore.models import LayoutChange
from mcwr.application.features.detach_restore.service import (
    detach_card,
    reclaim_children,
    restore_all,
    restore_card,
    toggle_collapse,
)
from mcwr.application.features.layout_board.ports import SizeEstimator
from mcwr.application.features.layout_board.service import (
    LinearLayoutOptions,
    layout_board,
    relayout_subtree,
)
from mcwr.application.features.load_document.models import LoadedDocument
from mcwr.application.features.persist_layout.ports import LayoutStore
from mcwr.application.features.persist_layout.service import persist_snapshot, restore_snapshot
from mcwr.application.features.refresh_document.service import plan_refresh
from mcwr.domain.errors import McwrError
from mcwr.domain.models import (
    SNAPSHOT_SCHEMA_VERSION,
    Block,
    BoardSnapshot,
    CardId,
    CardLayout,
    CardTree,
    Viewport,
    WindowState,
)
from mcwr.infrastructure.heuristic_sizer import HeuristicSizeEstimator


class BoardSession(QObject):
    """One window's reading state: the document, its layouts and the operations on them."""

    document_loaded = Signal()
    cards_changed = Signal(tuple)
    status = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        estimator: SizeEstimator | None = None,
        options: LinearLayoutOptions | None = None,
        store: LayoutStore | None = None,
        session_id: str = "",
        window_uuid: str = "",
    ) -> None:
        super().__init__(parent)
        self._estimator: SizeEstimator = estimator or HeuristicSizeEstimator()
        self._options = options or LinearLayoutOptions()
        self._store = store
        self._session_id = session_id or uuid.uuid4().hex
        self._window_uuid = window_uuid or uuid.uuid4().hex
        self._document: LoadedDocument | None = None
        self._layouts: dict[CardId, CardLayout] = {}
        self._viewport = Viewport()

    # ------------------------------------------------------------------ read side

    @property
    def document(self) -> LoadedDocument | None:
        return self._document

    @property
    def path(self) -> Path | None:
        return None if self._document is None else self._document.document.path

    @property
    def layouts(self) -> dict[CardId, CardLayout]:
        return self._layouts

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def window_uuid(self) -> str:
        return self._window_uuid

    @property
    def blocks(self) -> Mapping[int, Block]:
        if self._document is None:
            return {}
        return {block.index: block for block in self._document.blocks}

    def state_of(self, card_id: CardId) -> CardLayout | None:
        return self._layouts.get(card_id)

    @property
    def is_open(self) -> bool:
        return self._document is not None

    # ----------------------------------------------------------------- write side

    def open(self, path: Path) -> bool:
        """Load ``path``, restoring stored geometry when a session snapshot exists."""
        try:
            loaded = container.load(path)
        except McwrError as exc:
            self.failed.emit(str(exc))
            return False
        except Exception as exc:  # noqa: BLE001 - acceptance 10: never crash the window
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return False

        self._document = loaded
        stored: Mapping[CardId, CardLayout] = {}
        if self._store is not None:
            restored = restore_snapshot(
                loaded.document,
                store=self._store,
                session=self._session_id,
                window_uuid=self._window_uuid,
            )
            stored = restored.snapshot.layouts
            self._viewport = restored.snapshot.viewport
            for warning in restored.warnings:
                self.status.emit(f"warning: {warning}")
        restored_count = self._apply_layouts(stored)
        for warning in loaded.warnings:
            self.status.emit(f"warning: {warning}")
        self.document_loaded.emit()
        self.cards_changed.emit(tuple(self._layouts))
        self.status.emit(
            f"opened {loaded.document.path.name}: {len(loaded.tree.cards)} cards, "
            f"{len(loaded.blocks)} blocks, {restored_count} layouts restored"
        )
        return True

    def detach(self, card_id: CardId) -> LayoutChange:
        return self._apply(detach_card(self._tree(), self._layouts, card_id), card_id)

    def restore(self, card_id: CardId) -> LayoutChange:
        return self._apply(restore_card(self._tree(), self._layouts, card_id), card_id)

    def reclaim(self, card_id: CardId) -> LayoutChange:
        return self._apply(reclaim_children(self._tree(), self._layouts, card_id), card_id)

    def fold(self, card_id: CardId) -> LayoutChange:
        return self._apply(toggle_collapse(self._tree(), self._layouts, card_id), card_id)

    def restore_all(self) -> LayoutChange:
        """Rebuild the initial attached arrangement and reset the fold state (FR-4.5)."""
        if self._document is None:
            return LayoutChange()
        change = restore_all(self._tree(), self._layouts)
        self._layouts = layout_board(
            self._tree(), blocks=self.blocks, estimator=self._estimator, options=self._options
        )
        self.cards_changed.emit(tuple(self._layouts))
        self.status.emit("all cards restored to the initial arrangement")
        return change

    def move_card(self, card_id: CardId, x: float, y: float) -> None:
        """Record a finished drag (whiteboard coordinates)."""
        layout = self._layouts.get(card_id)
        if layout is None:
            return
        layout.move_to(x, y)

    def refresh(self) -> bool:
        """Re-read and re-parse the file on demand, structure first (FR-5, D11).

        Cards matched by their stable key keep their geometry, collapse and free-card
        state; a major structural change (big section count or heading level sequence)
        rebuilds the board instead, with a warning naming the reason.
        """
        if self._document is None:
            return False
        path = self._document.document.path
        previous_document = self._document
        previous_layouts = dict(self._layouts)
        try:
            loaded = container.load(path)
        except McwrError as exc:
            self.failed.emit(f"refresh failed, keeping the current view: {exc}")
            return False
        except Exception as exc:  # noqa: BLE001 - acceptance 10
            self.failed.emit(f"refresh failed ({type(exc).__name__}: {exc})")
            return False

        plan = plan_refresh(previous_document.tree, loaded.tree, previous_layouts)
        self._document = loaded
        for warning in plan.warnings:
            self.status.emit(f"warning: {warning}")
        new_count = self._apply_layouts({} if plan.major else plan.layouts)
        self.document_loaded.emit()
        self.cards_changed.emit(tuple(self._layouts))
        if plan.major:
            self.status.emit("结构变化较大，已按新结构重建")
        else:
            self.status.emit(f"已刷新：{len(loaded.tree.cards)} 张卡片（新增 {new_count}）")
        return True

    # --------------------------------------------------------------- persistence

    def set_viewport(
        self, scale: float, pan_x: float, pan_y: float, *, fitted: bool = True
    ) -> None:
        """Remember the canvas transform so a restart reopens at the same zoom (FR-7.3)."""
        self._viewport = Viewport(scale=scale, pan_x=pan_x, pan_y=pan_y, fitted_once=fitted)

    @property
    def viewport(self) -> Viewport:
        return self._viewport

    def persist(self) -> bool:
        """Write this document's snapshot for this session (never raises)."""
        if self._store is None or self._document is None:
            return False
        snapshot = BoardSnapshot(
            schema_version=SNAPSHOT_SCHEMA_VERSION,
            document=self._document.document,
            layouts=dict(self._layouts),
            viewport=self._viewport,
            window_uuid=self._window_uuid,
        )
        try:
            persist_snapshot(snapshot, store=self._store, session=self._session_id)
        except Exception as exc:  # noqa: BLE001 - a failed save must not break closing
            self.failed.emit(f"could not save the layout: {exc}")
            return False
        return True

    def load_window_state(self) -> WindowState | None:
        if self._store is None:
            return None
        try:
            return self._store.load_window(self._window_uuid)
        except Exception as exc:  # noqa: BLE001 - a bad window file must not block startup
            self.status.emit(f"warning: window state unusable ({exc})")
            return None

    def save_window_state(self, state: WindowState) -> None:
        if self._store is None:
            return
        try:
            self._store.save_window(state)
        except Exception as exc:  # noqa: BLE001 - closing must not fail
            self.status.emit(f"warning: could not save the window state ({exc})")

    # ------------------------------------------------------------------- internals

    def _tree(self) -> CardTree:
        if self._document is None:
            raise RuntimeError("no document is open")
        return self._document.tree

    def _apply(self, change: LayoutChange, card_id: CardId) -> LayoutChange:
        if change.reason:
            self.status.emit(change.reason)
        if change.relayout:
            self._relayout_from(card_id)
        return change

    def _apply_layouts(self, previous: Mapping[CardId, CardLayout]) -> int:
        """Lay the board out fresh, then overlay stored geometry; returns new-card count."""
        tree = self._tree()
        fresh = layout_board(
            tree, blocks=self.blocks, estimator=self._estimator, options=self._options
        )
        new_ids = [card_id for card_id in fresh if card_id not in previous]
        for card_id, layout in previous.items():
            target = fresh.get(card_id)
            if target is None:
                continue
            if layout.width <= 0.0 and layout.height <= 0.0:
                continue  # a placeholder (e.g. a brand-new card) keeps its fresh position
            target.x, target.y = layout.x, layout.y
            target.width, target.height = layout.width, layout.height
            target.collapsed = layout.collapsed
            target.detached = layout.detached
            target.manual_size = layout.manual_size
        self._layouts = fresh
        for parent in {tree.cards[card_id].parent_id for card_id in new_ids}:
            if parent is not None and parent in self._layouts:
                self._relayout_from(parent)
        return len(new_ids)

    def _relayout_from(self, card_id: CardId) -> None:
        """Re-stack the parent of ``card_id`` (or the card itself) after a change."""
        tree = self._tree()
        card = tree.cards.get(card_id)
        root = card.parent_id if card is not None and card.parent_id else card_id
        if root not in self._layouts:
            return
        self._layouts = relayout_subtree(
            tree,
            self._layouts,
            root,
            blocks=self.blocks,
            estimator=self._estimator,
            options=self._options,
        )
        self.cards_changed.emit(tuple(self._layouts))
