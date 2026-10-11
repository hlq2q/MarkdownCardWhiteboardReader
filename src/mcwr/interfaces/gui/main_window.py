"""Main window: whiteboard view, toolbar, bottom-right refresh / restore-all (FR-3–FR-5)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QResizeEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mcwr import container
from mcwr.application.features.detach_restore.service import can_detach
from mcwr.application.features.persist_layout.ports import LayoutStore
from mcwr.domain.models import CardId, WindowState
from mcwr.interfaces.gui.board_view import BoardScene, BoardView
from mcwr.interfaces.gui.card_item import CardItem
from mcwr.interfaces.gui.session import BoardSession

ZOOM_PRESETS = ("50", "75", "100", "125", "150", "200")


class MainWindow(QMainWindow):
    """One window = one independent session (FR-6.1/6.2)."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        store: LayoutStore | None = None,
        session_id: str = "",
        window_uuid: str = "",
        persist: bool = True,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Markdown Card Whiteboard Reader")
        self.resize(1400, 900)

        self._store = container.build_layout_store() if persist and store is None else store
        self.session = BoardSession(
            self, store=self._store, session_id=session_id, window_uuid=window_uuid
        )
        self.scene = BoardScene(self)
        self.view = BoardView(self.scene, self)
        self.setCentralWidget(self.view)
        self._items: dict[CardId, CardItem] = {}
        self._zoom_box: QComboBox | None = None
        self._overlay = QWidget(self)

        self._build_actions()
        self._build_overlay()
        self._connect()
        self._restore_window_state()
        self.statusBar().showMessage("open a Markdown file to begin (Ctrl+O)")

        if path is not None:
            self.open_path(path)

    # ------------------------------------------------------------ window state

    def _restore_window_state(self) -> None:
        """Reopen at the stored size, zoom and document (spec §4 F8)."""
        state = self.session.load_window_state()
        if state is None:
            return
        self.resize(state.width, state.height)
        self.move(state.x, state.y)
        if state.maximized:
            self.showMaximized()
        if state.active_document:
            last = Path(state.active_document)
            if last.is_file():
                self.open_path(last)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Persist the layout and the window state before the window goes away (FR-7.3)."""
        self.session.set_viewport(
            self.view.zoom_percent() / 100.0,
            float(self.view.horizontalScrollBar().value()),
            float(self.view.verticalScrollBar().value()),
        )
        self.session.persist()
        active = str(self.session.path) if self.session.path is not None else None
        self.session.save_window_state(
            WindowState(
                window_uuid=self.session.window_uuid,
                x=self.x(),
                y=self.y(),
                width=self.width(),
                height=self.height(),
                maximized=self.isMaximized(),
                open_documents=(active,) if active else (),
                active_document=active,
            )
        )
        super().closeEvent(event)

    # ------------------------------------------------------------------ UI pieces

    def _build_actions(self) -> None:
        self.action_open = _action(self, "打开…", "Ctrl+O", self._choose_file)
        self.action_refresh = _action(self, "刷新", "F5", self._refresh)
        self.action_restore_all = _action(self, "全部还原", "Ctrl+Shift+R", self._restore_all)
        self.action_fit = _action(self, "适应视图", "Ctrl+0", self._fit)
        self.action_zoom_in = _action(self, "放大", "Ctrl+=", lambda: self.view.zoom_by(1.25))
        self.action_zoom_out = _action(self, "缩小", "Ctrl+-", lambda: self.view.zoom_by(0.8))

        toolbar = self.addToolBar("view")
        toolbar.setMovable(False)
        toolbar.addAction(self.action_open)
        toolbar.addAction(self.action_refresh)
        toolbar.addAction(self.action_restore_all)
        toolbar.addSeparator()
        toolbar.addAction(self.action_zoom_out)
        toolbar.addAction(self.action_zoom_in)
        toolbar.addAction(self.action_fit)
        toolbar.addSeparator()
        toolbar.addWidget(self._build_zoom_box())

    def _build_zoom_box(self) -> QComboBox:
        box = QComboBox(self)
        box.setEditable(True)
        box.addItems(ZOOM_PRESETS)
        box.setCurrentText("100")
        box.setFixedWidth(90)
        box.activated.connect(lambda: self.view.set_zoom(_percent(box.currentText())))
        line_edit = box.lineEdit()
        if line_edit is not None:
            line_edit.editingFinished.connect(
                lambda: self.view.set_zoom(_percent(box.currentText()))
            )
        self._zoom_box = box
        return box

    def _build_overlay(self) -> None:
        """Bottom-right buttons required by FR-4.5 and FR-5.1."""
        layout = QVBoxLayout(self._overlay)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        refresh = QPushButton("刷新", self._overlay)
        restore = QPushButton("全部还原", self._overlay)
        refresh.clicked.connect(self._refresh)
        restore.clicked.connect(self._restore_all)
        row.addWidget(refresh)
        row.addWidget(restore)
        layout.addLayout(row)
        self._overlay.adjustSize()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        size = self._overlay.sizeHint()
        self._overlay.resize(size)
        central = self.centralWidget()
        if central is not None:
            self._overlay.move(
                central.width() - size.width() - 18,
                central.height() - size.height() - 18,
            )

    def _connect(self) -> None:
        self.session.document_loaded.connect(self._rebuild_items)
        self.session.cards_changed.connect(self._apply_geometry)
        self.session.status.connect(self.statusBar().showMessage)
        self.session.failed.connect(self._show_failure)
        self.view.zoom_changed.connect(self._on_zoom_changed)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._show_context_menu)

    # ------------------------------------------------------------------ documents

    @property
    def card_items(self) -> dict[CardId, CardItem]:
        """The scene items, keyed by card id (read-only view for tests and tools)."""
        return dict(self._items)

    def open_path(self, path: Path) -> bool:
        opened = self.session.open(path)
        if opened:
            self.setWindowTitle(f"{path.name} — Markdown Card Whiteboard Reader")
            self.view.fit_cards()
        return opened

    def _choose_file(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self, "打开 Markdown 文件", "", "Markdown (*.md *.markdown *.mdx);;所有文件 (*)"
        )
        if selected:
            self.open_path(Path(selected))

    def _refresh(self) -> None:
        if not self.session.is_open:
            self.statusBar().showMessage("nothing to refresh: open a file first")
            return
        self.session.refresh()

    def _restore_all(self) -> None:
        if self.session.is_open:
            self.session.restore_all()
            self.view.fit_cards()

    def _fit(self) -> None:
        self.view.fit_cards()

    def _show_failure(self, message: str) -> None:
        self.statusBar().showMessage(f"error: {message}")

    # -------------------------------------------------------------------- drawing

    def _rebuild_items(self) -> None:
        for item in self._items.values():
            self.scene.removeItem(item)
        self._items.clear()
        document = self.session.document
        if document is None:
            return
        blocks = self.session.blocks
        for card_id in document.tree.ordered_ids():
            card = document.tree.cards[card_id]
            layout = self.session.layouts.get(card_id)
            if layout is None:
                continue
            item = CardItem(card, blocks, layout)
            item.moved.connect(self._on_item_moved)
            self._items[card_id] = item
        self._reparent_items()
        self._apply_geometry(tuple(self._items))

    def _reparent_items(self) -> None:
        """Attach each item to its parent item unless the card is a free card (FR-4.2)."""
        document = self.session.document
        if document is None:
            return
        for card_id in reversed(document.tree.ordered_ids()):
            item = self._items.get(card_id)
            layout = self.session.layouts.get(card_id)
            if item is None or layout is None:
                continue
            parent_id = document.tree.cards[card_id].parent_id
            parent_item = self._items.get(parent_id) if parent_id else None
            if layout.detached or parent_item is None:
                scene_position = item.scenePos()
                item.setParentItem(None)  # type: ignore[arg-type]  # None detaches in Qt
                if item.scene() is None:
                    self.scene.addItem(item)
                item.setPos(scene_position)
            else:
                item.setParentItem(parent_item)

    def _apply_geometry(self, card_ids: tuple[CardId, ...]) -> None:
        """Push domain coordinates into Qt items (parents first, children offset)."""
        document = self.session.document
        if document is None or not self._items:
            return  # nothing is drawn yet; _rebuild_items applies geometry afterwards
        self._reparent_items()
        for card_id in card_ids:
            item = self._items.get(card_id)
            layout = self.session.layouts.get(card_id)
            if item is None or layout is None:
                continue
            item.set_card_geometry(layout.width, layout.height)
            item.setZValue(float(layout.z))
            parent_item = item.parentItem()
            offset = parent_item.scenePos() if parent_item is not None else QPointF(0.0, 0.0)
            item.setPos(QPointF(layout.x - offset.x(), layout.y - offset.y()))
            item.setVisible(not self._is_hidden(card_id))

    def _on_item_moved(self, item: object, x: float, y: float) -> None:
        if isinstance(item, CardItem):
            self.session.move_card(item.card.card_id, x, y)
            self.statusBar().showMessage(f"moved {item.card.title!r} to ({x:.0f}, {y:.0f})")

    def _on_zoom_changed(self, percent: float) -> None:
        if self._zoom_box is not None:
            self._zoom_box.setCurrentText(f"{percent:.0f}")
        self.session.set_viewport(
            percent / 100.0,
            float(self.view.horizontalScrollBar().value()),
            float(self.view.verticalScrollBar().value()),
        )

    def _is_hidden(self, card_id: CardId) -> bool:
        """A card inside a folded ancestor is hidden but keeps its remembered geometry."""
        document = self.session.document
        if document is None:
            return False
        for ancestor in document.tree.ancestors(card_id):
            layout = self.session.layouts.get(ancestor)
            if layout is not None and layout.collapsed:
                return True
        return False

    # ---------------------------------------------------------------- context menu

    def _show_context_menu(self, position: QPoint) -> None:
        item = self.view.itemAt(position)
        menu = QMenu(self)
        if isinstance(item, CardItem):
            self._fill_card_menu(menu, item.card.card_id)
            menu.addSeparator()
        menu.addAction(self.action_refresh)
        menu.addAction(self.action_restore_all)
        menu.addAction(self.action_fit)
        menu.exec(self.view.viewport().mapToGlobal(position))

    def _fill_card_menu(self, menu: QMenu, card_id: CardId) -> None:
        document = self.session.document
        if document is None:
            return
        tree = document.tree
        layouts = self.session.layouts
        layout = layouts.get(card_id)
        detached = bool(layout is not None and layout.detached)

        detach = menu.addAction("拖出为自由卡片")
        detach.setEnabled(can_detach(tree, card_id) and not detached)
        detach.triggered.connect(lambda: self.session.detach(card_id))

        restore = menu.addAction("还原到父卡片")
        restore.setEnabled(detached)
        restore.triggered.connect(lambda: self.session.restore(card_id))

        reclaim = menu.addAction("收回所有子卡片")
        reclaim.setEnabled(
            any(
                layouts[child].detached
                for child in tree.descendants(card_id)
                if child in layouts
            )
        )
        reclaim.triggered.connect(lambda: self.session.reclaim(card_id))

        fold = menu.addAction("折叠 / 展开")
        fold.setEnabled(bool(tree.cards[card_id].child_ids))
        fold.triggered.connect(lambda: self.session.fold(card_id))


def _action(
    window: MainWindow, text: str, shortcut: str, slot: Callable[[], None]
) -> QAction:
    action = QAction(text, window)
    action.setShortcut(QKeySequence(shortcut))
    action.triggered.connect(slot)
    return action


def _percent(text: str) -> float:
    try:
        return float(text.strip().rstrip("%"))
    except ValueError:
        return 100.0
