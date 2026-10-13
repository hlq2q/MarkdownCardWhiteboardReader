"""Board session: owns one open document plus its layout state for one window (FR-6.2).

This is the MVVM boundary: Qt signals outward, application use cases inward. It never
touches widgets, and it is the only place that knows about persistence, so the window
class stays a thin binding layer.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from PySide6.QtCore import QObject, Signal

from mcwr import container
from mcwr.application.features.build_toc.models import TocEntry
from mcwr.application.features.build_toc.service import build_toc
from mcwr.application.features.detach_restore.models import LayoutChange
from mcwr.application.features.detach_restore.service import (
    detach_card,
    expand_ancestors,
    reclaim_children,
    restore_all,
    restore_card,
    toggle_collapse,
)
from mcwr.application.features.layout_board.grid import snap_to_grid
from mcwr.application.features.layout_board.neighbours import Box, snap_delta
from mcwr.application.features.layout_board.ports import SizeEstimator
from mcwr.application.features.layout_board.service import (
    LinearLayoutOptions,
    layout_board,
    relayout_subtree,
)
from mcwr.application.features.layout_board.stack import (
    hug_all,
    move_subtree,
    propagate_height,
    resolve_overlaps,
)
from mcwr.application.features.load_document.models import LoadedDocument
from mcwr.application.features.persist_layout.ports import LayoutStore
from mcwr.application.features.persist_layout.service import persist_snapshot, restore_snapshot
from mcwr.application.features.refresh_document.service import plan_refresh
from mcwr.domain.errors import McwrError
from mcwr.domain.models import (
    MAX_CARDS,
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
from mcwr.infrastructure.measured_sizer import MeasuredHeightEstimator


def limit_notice(card_count: int) -> str:
    """The degraded-mode notice sent once per load (D-023/D-029).

    The window shortens it before it reaches the status bar; the full sentence stays here so
    both the open and the refresh path say exactly the same thing.
    """
    return f"超限：{card_count} 张卡片（上限 {MAX_CARDS}），公式/图表按原文显示"


MIN_SCALE: Final[float] = 0.5
"""Smallest factor a free card may be scaled to (T-057)."""

MAX_SCALE: Final[float] = 3.0
"""Largest factor a free card may be scaled to (T-057)."""


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
        # Body heights measured from the real documents, keyed by card id (T-049). Card ids follow
        # the content, so a stale entry can only ever belong to a card that renders the same way.
        self._measured: dict[CardId, float] = {}
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

    @property
    def card_count(self) -> int:
        """Cards in the open document, or 0 when nothing is open (T-025 acceptance ①)."""
        return 0 if self._document is None else self._document.card_count

    @property
    def over_limit(self) -> bool:
        """Whether the open document exceeds ``MAX_CARDS``, i.e. runs in degraded mode.

        D-029: past the limit the offscreen math/diagram rendering is switched off and those
        cards keep their source text; every other feature behaves normally.
        """
        return self._document is not None and self._document.over_limit

    @property
    def toc(self) -> tuple[TocEntry, ...]:
        """The TOC card's entries for the open document, recomputed from its card tree.

        Computed, never stored: the entries are a pure function of the tree, so a refresh can
        never leave a stale table of contents behind (FR-2.4).
        """
        return () if self._document is None else build_toc(self._document.tree)

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
        if loaded.over_limit:
            self.status.emit(limit_notice(loaded.card_count))
        return True

    def detach(self, card_id: CardId) -> LayoutChange:
        return self._apply(detach_card(self._tree(), self._layouts, card_id), card_id)

    def restore(self, card_id: CardId) -> LayoutChange:
        """Put a card back into its parent, at its natural size (T-057/D-053).

        A scaled card is reset first: one going back into the column must not carry a size the column
        cannot hold -- the mistake the user asked to avoid.
        """
        if self.reset_scale(card_id):
            self.status.emit("the card was scaled back before restoring it")
        return self._apply(restore_card(self._tree(), self._layouts, card_id), card_id)

    def reclaim(self, card_id: CardId) -> LayoutChange:
        return self._apply(reclaim_children(self._tree(), self._layouts, card_id), card_id)

    def fold(self, card_id: CardId) -> LayoutChange:
        return self._apply(toggle_collapse(self._tree(), self._layouts, card_id), card_id)

    def reveal(self, card_id: CardId) -> int:
        """Unfold the ancestors hiding ``card_id``; returns how many were opened (FR-2.4).

        The caller centers the viewport on the card afterwards; this method only makes it
        reachable, so a TOC jump into a folded section shows the card instead of a blank area.
        """
        if self._document is None:
            return 0
        change = expand_ancestors(self._tree(), self._layouts, card_id)
        if change.changed:
            self.cards_changed.emit(tuple(self._layouts))
        return len(change.affected)

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

    def move_card(self, card_id: CardId, x: float, y: float, *, snap: bool = False) -> None:
        """Record a finished drag of a card that is allowed to move (T-043, D-050).

        A card inside its parent keeps its position relative to that parent — the user's rule is
        that it is frozen and only travels when the parent does — so a new position is accepted
        only for free cards and for parentless (top-level) cards. Everything attached below the
        moved card follows by the same delta, which keeps the stored geometry equal to what the
        view shows, now and after a reload.

        ``snap`` pulls the position onto the whiteboard grid first (T-048, D-051): each axis moves
        only when the drop is close enough to a line, so a deliberate off-grid spot is kept.
        """
        layout = self._layouts.get(card_id)
        tree = self._tree()
        card = tree.cards.get(card_id)
        if layout is None or card is None:
            return
        if card.parent_id is not None and not layout.detached:
            return
        if snap:
            # Edges first, the grid second -- the same rule a group drop follows (D-051/D-052).
            dx, dy = self._snapped_group_delta([card_id], x - layout.x, y - layout.y)
            x, y = layout.x + dx, layout.y + dy
        delta_x, delta_y = x - layout.x, y - layout.y
        layout.move_to(x, y)
        for child in card.child_ids:
            move_subtree(tree, self._layouts, child, delta_x, delta_y)
        self.cards_changed.emit(tuple(self._layouts))

    def move_cards(
        self, card_ids: Sequence[CardId], delta_x: float, delta_y: float, *, snap: bool = True
    ) -> None:
        """Move a group of free cards by a scene delta, snapping the drop (T-051/D-052).

        A group drag follows the rules of a single one: only free and parentless cards move, what is
        attached below them follows by the same delta, and the drop snaps -- edges first, the grid
        second -- on the group's bounding box so the relative arrangement inside it is untouched.
        """
        tree = self._tree()
        movable = [
            card_id
            for card_id in card_ids
            if (layout := self._layouts.get(card_id)) is not None
            and (card := tree.cards.get(card_id)) is not None
            and (card.parent_id is None or layout.detached)
        ]
        if not movable:
            return
        if snap:
            delta_x, delta_y = self._snapped_group_delta(movable, delta_x, delta_y)
            if not delta_x and not delta_y:
                return
        elif not delta_x and not delta_y:
            return
        for card_id in movable:
            layout = self._layouts[card_id]
            layout.move_to(layout.x + delta_x, layout.y + delta_y)
            for child in tree.cards[card_id].child_ids:
                move_subtree(tree, self._layouts, child, delta_x, delta_y)
        self.cards_changed.emit(tuple(self._layouts))

    def _snapped_group_delta(
        self, card_ids: Sequence[CardId], delta_x: float, delta_y: float
    ) -> tuple[float, float]:
        """Edges first, then the grid, for the group's bounding box (D-051/D-052)."""
        boxes = [self._box_of(card_id) for card_id in card_ids]
        left = min(box[0] for box in boxes) + delta_x
        top = min(box[1] for box in boxes) + delta_y
        right = max(box[0] + box[2] for box in boxes) + delta_x
        bottom = max(box[1] + box[3] for box in boxes) + delta_y
        moving: Box = (left, top, right - left, bottom - top)
        edge_x, edge_y = snap_delta(moving, self._other_boxes(card_ids))
        if edge_x or edge_y:
            return delta_x + edge_x, delta_y + edge_y
        grid_x, grid_y = snap_to_grid(left, top)
        return delta_x + (grid_x - left), delta_y + (grid_y - top)

    def _box_of(self, card_id: CardId) -> Box:
        layout = self._layouts[card_id]
        return (layout.x, layout.y, layout.width, layout.height)

    def _other_boxes(self, card_ids: Sequence[CardId]) -> list[Box]:
        """Every card that is not part of the move: the neighbours a drop can land against."""
        skipped = set(card_ids)
        for card_id in card_ids:
            skipped.update(self._tree().descendants(card_id))
        return [self._box_of(other) for other in self._layouts if other not in skipped]

    def scale_card(self, card_id: CardId, factor: float) -> bool:
        """Scale one free card's subtree by ``factor``; whether anything changed (T-057/D-053).

        Only a card the user pulled out carries a factor of its own: one inside its parent gets its
        width from the column, and a parentless card is the board's frame. The factor widens it,
        so everything placed inside it is laid out in the wider box and scales along.
        """
        layout = self._layouts.get(card_id)
        card = self._tree().cards.get(card_id)
        if layout is None or card is None or not layout.detached:
            return False
        scaled = min(max(layout.scale * factor, MIN_SCALE), MAX_SCALE)
        if abs(scaled - layout.scale) < 1e-6:
            return False
        base_width = layout.width / (layout.scale or 1.0)
        layout.scale = scaled
        self._relayout_free(card_id, base_width=base_width)
        return True

    def reset_scale(self, card_id: CardId) -> bool:
        """Give a free card its natural size back; whether it had been scaled (T-057)."""
        layout = self._layouts.get(card_id)
        if layout is None or layout.scale == 1.0:
            return False
        base_width = layout.width / (layout.scale or 1.0)
        layout.scale = 1.0
        self._relayout_free(card_id, base_width=base_width)
        return True

    def _relayout_free(self, card_id: CardId, *, base_width: float | None = None) -> None:
        """Re-stack a free card (with its subtree) in place and republish the board state."""
        tree = self._tree()
        self._layouts = relayout_subtree(
            tree,
            self._layouts,
            card_id,
            blocks=self.blocks,
            estimator=self._layout_estimator(),
            options=self._options,
            base_width=base_width,
        )
        resolve_overlaps(tree, self._layouts, all_parents=True, options=self._options)
        hug_all(tree, self._layouts)
        self.cards_changed.emit(tuple(self._layouts))

    def refresh(self) -> bool:
        """Re-read and re-parse the file on demand, structure first (FR-5, D11).

        Cards matched by their stable key keep their geometry, collapse and free-card
        state; a major structural change (top-level card count or heading level sequence)
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
        if loaded.over_limit:
            self.status.emit(limit_notice(loaded.card_count))
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

    def adopt_measured_heights(self, measured: Mapping[CardId, float]) -> None:
        """Lay the board out again with the body heights the cards really rendered (T-049).

        The text estimator can only guess -- it does not know that a fenced block's ``` lines are
        not body lines, or how tall a rendered table row is -- and ``CardItem.paint`` clips the body
        to the card's height, so a guess that is too small hides rows and one that is too large
        leaves padding. The view measures its documents and calls this; positions, collapsed and
        detached state survive, every manually sized card keeps its size, and the column is packed
        again around the real heights.
        """
        if not measured or not self._layouts:
            return
        # A measured height is what the card *rendered* at, factor included, while the placer
        # multiplies by the effective factor again (T-064/D-060). Store the base height so the two
        # multiplications never stack up -- E-033: every refresh made a scaled card taller.
        self._measured = {
            card_id: height / (layout.effective_scale or 1.0)
            if (layout := self._layouts.get(card_id)) is not None
            else height
            for card_id, height in measured.items()
        }
        kept = [
            card_id
            for card_id, layout in self._layouts.items()
            if (card := self._tree().cards.get(card_id)) is not None
            and (card.parent_id is None or layout.detached)
        ]
        self._apply_layouts(self._layouts, keep_sizes=False)
        # Every position that was kept has to take its own subtree with it: the pass above packs the
        # children around the *new* heights, so a kept parent whose content grew would otherwise end
        # up below children that were placed against its old box (E-031). The re-stack is per card
        # and the sweeps run once afterwards -- one full overlap sweep per card turned a 1000-card
        # document into an O(n^2) pass (measured 10.3 s in test_card_limit, T-055).
        tree = self._tree()
        estimator = self._layout_estimator()
        for card_id in kept:
            card = tree.cards.get(card_id)
            if card is None or not card.child_ids or card_id not in self._layouts:
                continue
            root = card.parent_id if card.parent_id else card_id
            before = self._layouts[root].height
            self._layouts = relayout_subtree(
                tree,
                self._layouts,
                root,
                blocks=self.blocks,
                estimator=estimator,
                options=self._options,
            )
            propagate_height(tree, self._layouts, root, self._layouts[root].height - before)
        resolve_overlaps(tree, self._layouts, all_parents=True, options=self._options)
        hug_all(tree, self._layouts)
        self.cards_changed.emit(tuple(self._layouts))

    def _layout_estimator(self) -> SizeEstimator:
        """The heights the cards really rendered when the view has measured them (T-049).

        Every layout path goes through here -- a fresh layout, a structural re-stack, "restore all"
        -- because falling back to the raw text estimate after the first measurement would hand back
        the phantom padding and the clipped table that the measurement just removed.
        """
        if not self._measured:
            return self._estimator
        return MeasuredHeightEstimator(self._estimator, self._measured)

    def _apply_layouts(
        self, previous: Mapping[CardId, CardLayout], *, keep_sizes: bool = True
    ) -> int:
        """Lay the board out fresh, then overlay stored geometry; returns new-card count.

        With ``keep_sizes=False`` the stored *sizes* give way to the fresh ones, which is what the
        measured-height pass needs. Such a pass also re-packs the attached cards instead of pinning
        them to their stored y: a card inside its parent cannot be moved by the user, so its
        position is layout output rather than user state -- and pinning it while its parent's own
        height grew left the column a few pixels short of the tight stacking (E-029). Only what the
        user can actually move -- a parentless card, or one already detached -- keeps its position.
        """
        tree = self._tree()
        fresh = layout_board(
            tree,
            blocks=self.blocks,
            estimator=self._layout_estimator(),
            options=self._options,
            states=previous,
        )
        new_ids = [card_id for card_id in fresh if card_id not in previous]
        for card_id, layout in previous.items():
            target = fresh.get(card_id)
            card = tree.cards.get(card_id)
            if target is None or card is None:
                continue
            if layout.width <= 0.0 and layout.height <= 0.0:
                continue  # a placeholder (e.g. a brand-new card) keeps its fresh position
            if keep_sizes or card.parent_id is None or layout.detached:
                target.x, target.y = layout.x, layout.y
            target.collapsed = layout.collapsed
            target.detached = layout.detached
            target.manual_size = layout.manual_size
            target.scale = layout.scale
            if keep_sizes or layout.manual_size:
                target.width, target.height = layout.width, layout.height
        self._layouts = fresh
        # A stored arrangement can carry overlaps (an older snapshot, a manual drag that was
        # never followed by a structural change), and opening/refreshing is the moment the
        # user expects the stacking to be sane again (T-036, D-045).
        resolve_overlaps(tree, self._layouts, all_parents=True, options=self._options)
        hug_all(tree, self._layouts)
        for parent in {tree.cards[card_id].parent_id for card_id in new_ids}:
            if parent is not None and parent in self._layouts:
                self._relayout_from(parent)
        return len(new_ids)

    def _relayout_from(self, card_id: CardId) -> None:
        """Re-stack the parent of ``card_id`` (or the card itself) after a change.

        Three follow-ups keep the column tight (T-036/T-041, D-045/D-048): the height change is
        carried up the ancestor chain, so no hole is left inside a grandparent and the cards
        after it follow; every parent is swept for overlapping siblings; and every box is pulled
        onto its lowest attached child — a structural operation is exactly the moment at which
        the user wants the stacking restored.
        """
        tree = self._tree()
        card = tree.cards.get(card_id)
        root = card.parent_id if card is not None and card.parent_id else card_id
        if root not in self._layouts:
            return
        before = self._layouts[root].height
        self._layouts = relayout_subtree(
            tree,
            self._layouts,
            root,
            blocks=self.blocks,
            estimator=self._estimator,
            options=self._options,
        )
        delta = self._layouts[root].height - before
        if delta and not self._layouts[root].detached:
            # A free card floats: it is not part of its parent's flow any more, so its own size
            # change must not be carried up the ancestor chain. Doing that collapsed A to 0 while
            # its item stayed 34 px tall -- the blank line where B used to be (E-034).
            propagate_height(tree, self._layouts, root, delta)
        resolve_overlaps(tree, self._layouts, all_parents=True, options=self._options)
        hug_all(tree, self._layouts)
        self.cards_changed.emit(tuple(self._layouts))
