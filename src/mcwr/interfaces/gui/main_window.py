"""Main window: whiteboard view, toolbar, bottom-right refresh / restore-all (FR-3–FR-5)."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Final, cast

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPushButton,
    QToolBar,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mcwr import PRODUCT_NAME, container
from mcwr.application.features.build_toc.models import TocEntry
from mcwr.application.features.build_toc.service import resolve_anchor
from mcwr.application.features.detach_restore.service import can_detach
from mcwr.application.features.persist_layout.ports import LayoutStore
from mcwr.application.features.render_card.ports import WebCardRenderer
from mcwr.application.features.render_card.service import card_image, needs_web_render
from mcwr.application.features.search_cards.models import SearchHit
from mcwr.application.features.search_cards.service import search_cards
from mcwr.domain.models import MAX_CARDS, CardId, WindowState
from mcwr.interfaces.gui.board_view import BoardScene, BoardView
from mcwr.interfaces.gui.card_item import CardItem
from mcwr.interfaces.gui.session import BoardSession
from mcwr.interfaces.gui.theme import (
    LIGHT,
    MIN_LEGIBLE_ON_SCREEN_WIDTH,
    Palette,
    Theme,
    ThemeMode,
    palette_for,
    resolve_theme,
    system_is_dark,
)
from mcwr.shared.config import load_theme_mode, save_theme_mode
from mcwr.shared.logging import logger, shorten

ZOOM_PRESETS = ("50", "75", "100", "125", "150", "200")

SCROLL_QUEUE_DELAY_MS: Final[int] = 180
"""How long the viewport must settle before the render queue is recomputed while scrolling."""

MAX_LIVE_PIXMAPS: Final[int] = 256
"""Cap on the in-memory rasters; scrolling far away releases the ones left behind (T-031)."""

OUTLINE_SHORTCUT: Final[str] = "Ctrl+B"
"""Collapse/expand the outline sidebar (T-032); the panel also carries a "收起" button."""

OVERLAY_MARGIN: Final[int] = 18
"""Gap between the floating buttons and the bottom-right corner of the board (T-035, D-044).

Deliberately wider than the scroll bar's 14 px ``sizeHint``, so the strip never sits on
top of it; the user picked this value and visual-spec §4 records it.
"""

THEME_CHOICES: tuple[tuple[ThemeMode, str], ...] = (
    (ThemeMode.SYSTEM, "跟随系统"),
    (ThemeMode.LIGHT, "浅色"),
    (ThemeMode.DARK, "深色"),
)
"""The three states of D-030; the labels are what the toolbar shows."""


class MainWindow(QMainWindow):
    """One window = one independent session (FR-6.1/6.2)."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        store: LayoutStore | None = None,
        renderer: WebCardRenderer | None = None,
        session_id: str = "",
        window_uuid: str = "",
        persist: bool = True,
    ) -> None:
        super().__init__()
        self.setWindowTitle(PRODUCT_NAME)
        self.resize(1400, 900)

        self._persist = persist
        self._store = container.build_layout_store() if persist and store is None else store
        self.session = BoardSession(
            self, store=self._store, session_id=session_id, window_uuid=window_uuid
        )
        self._theme_mode: ThemeMode = ThemeMode.SYSTEM
        self._theme: Theme = LIGHT.theme
        self._palette: Palette = LIGHT
        self.scene = BoardScene(self, LIGHT)
        self.view = BoardView(self.scene, self)
        self.setCentralWidget(self.view)
        self._items: dict[CardId, CardItem] = {}
        self._toc: tuple[TocEntry, ...] = ()
        self._outline: QTreeWidget | None = None
        self._outline_dock: QDockWidget | None = None
        self._outline_collapse: QToolButton | None = None
        self._outline_action: QAction | None = None
        self._toolbar: QToolBar | None = None
        self._search_box: QLineEdit | None = None
        self._hits: tuple[SearchHit, ...] = ()
        self._hit_index = -1
        self._hit_query = ""
        self._zoom_box: QComboBox | None = None
        self._theme_box: QComboBox | None = None
        self._overlay = QWidget(self)
        self._renderer = renderer
        self._renderer_error = ""
        self._pixmaps: dict[tuple[CardId, float, str], QPixmap] = {}
        self._image_queue: list[CardId] = []
        self._image_timer = QTimer(self)
        self._image_timer.setSingleShot(True)
        self._image_timer.timeout.connect(self._render_next_body)
        self._zoom_timer = QTimer(self)
        self._zoom_timer.setSingleShot(True)
        self._zoom_timer.timeout.connect(self._queue_body_images)
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.timeout.connect(self._queue_body_images)
        self._render_candidates: set[CardId] = set()

        self._build_actions()
        self._build_outline()
        self._build_overlay()
        self._connect()
        # The theme is applied before any document opens, so the first raster is already
        # produced in the right colours (the image is theme-specific, spec §5).
        self.apply_theme(load_theme_mode() if persist else ThemeMode.SYSTEM, remember=False)
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

    # ---------------------------------------------------------------------- theme

    @property
    def theme(self) -> Theme:
        """The theme currently in use (``light`` or ``dark``)."""
        return self._theme

    @property
    def theme_mode(self) -> ThemeMode:
        """What the user picked: ``system``, ``light`` or ``dark``."""
        return self._theme_mode

    @property
    def visual_palette(self) -> Palette:
        """The palette currently in use (read-only view for tests).

        Not named ``palette``: ``QWidget.palette()`` is Qt's ``QPalette`` accessor.
        """
        return self._palette

    def apply_theme(self, mode: ThemeMode | str, *, remember: bool = True) -> Theme:
        """Switch the whole window to ``mode`` and return the resolved theme (T-024 ③).

        Only drawing changes: the canvas, every existing card and the render queue are
        repainted/re-queued, while the document, the card tree and **every** ``CardLayout``
        field stay exactly as they were. ``system`` resolves through the Windows app theme
        (D-030); the choice is stored in the application data directory.
        """
        wanted = ThemeMode(str(mode))
        theme = resolve_theme(wanted, system_dark=system_is_dark())
        palette = palette_for(theme)
        self._theme_mode = wanted
        self._theme = theme
        self._palette = palette
        self.scene.set_palette(palette)
        for item in self._items.values():
            item.set_palette(palette)
        self._apply_window_palette(palette)
        self._sync_theme_box()
        if remember and self._persist and not save_theme_mode(wanted.value):
            logger().warning("the theme preference could not be saved")
        # The raster is theme-specific (spec §5): drop the other theme's pixmaps, hide the
        # now-mismatched images and let the queue re-render them in the new colours.
        self._pixmaps = {
            key: value for key, value in self._pixmaps.items() if key[2] == theme.value
        }
        for card_id, item in self._items.items():
            if (card_id, self._current_bucket(), theme.value) not in self._pixmaps:
                item.set_image(None)
        self._queue_body_images()
        return theme

    def _apply_window_palette(self, palette: Palette) -> None:
        """Chrome colours: window, toolbar, status bar, the outline dock and its widgets."""
        self.setStyleSheet(
            "QMainWindow, QToolBar, QStatusBar, QDockWidget "
            f"{{ background: {palette.app_bg}; color: {palette.text_primary}; }} "
            "QTreeWidget "
            f"{{ background: {palette.app_bg}; color: {palette.text_primary}; "
            f"border: 1px solid {palette.border}; }} "
            "QTreeWidget::item:selected "
            f"{{ background: {palette.selected}; color: {palette.card_bg}; }} "
            "QToolButton#outlineCollapse "
            f"{{ color: {palette.text_primary}; background: {palette.app_bg}; "
            f"border: 1px solid {palette.border}; border-radius: 3px; padding: 1px 6px; }} "
            "QToolButton#outlineCollapse:hover "
            f"{{ background: {palette.card_bg}; border-color: {palette.selected}; }}"
        )

    def _sync_theme_box(self) -> None:
        """Show the current mode without re-triggering the switch (``activated`` only)."""
        box = self._theme_box
        if box is None:
            return
        index = next(
            (i for i, (mode, _) in enumerate(THEME_CHOICES) if mode is self._theme_mode), 0
        )
        if box.currentIndex() != index:
            box.setCurrentIndex(index)

    def _follow_the_system_scheme(self) -> None:
        """Re-resolve ``跟随系统`` when Windows flips light/dark while the app runs."""
        from PySide6.QtGui import QGuiApplication

        existing = QGuiApplication.instance()
        if existing is None:  # pragma: no cover - a window implies a QApplication
            return
        hints = cast(QGuiApplication, existing).styleHints()
        changed = getattr(hints, "colorSchemeChanged", None)
        if callable(changed):
            changed.connect(self._on_system_scheme_changed)

    def _on_system_scheme_changed(self) -> None:
        if self._theme_mode is ThemeMode.SYSTEM:
            self.apply_theme(ThemeMode.SYSTEM, remember=False)

    # ------------------------------------------------------------------ UI pieces

    def _build_actions(self) -> None:
        self.action_open = _action(self, "打开…", "Ctrl+O", self._choose_file)
        self.action_new_window = _action(self, "新建窗口", "Ctrl+N", self._new_window)
        self.action_refresh = _action(self, "刷新", "F5", self._refresh)
        self.action_restore_all = _action(self, "全部还原", "Ctrl+Shift+R", self._restore_all)
        self.action_fit = _action(self, "适应视图", "Ctrl+0", self._fit)
        self.action_zoom_in = _action(self, "放大", "Ctrl+=", lambda: self.view.zoom_by(1.25))
        self.action_zoom_out = _action(self, "缩小", "Ctrl+-", lambda: self.view.zoom_by(0.8))
        self.action_snap = _action(self, "吸附到网格", "", self._toggle_snap)
        self.action_snap.setCheckable(True)
        self.action_snap.setChecked(True)

        toolbar = self.addToolBar("view")
        toolbar.setMovable(False)
        self._toolbar = toolbar
        toolbar.addAction(self.action_new_window)
        toolbar.addAction(self.action_open)
        toolbar.addAction(self.action_refresh)
        toolbar.addAction(self.action_restore_all)
        toolbar.addSeparator()
        toolbar.addAction(self.action_zoom_out)
        toolbar.addAction(self.action_zoom_in)
        toolbar.addAction(self.action_fit)
        toolbar.addAction(self.action_snap)
        toolbar.addSeparator()
        toolbar.addWidget(self._build_zoom_box())
        toolbar.addSeparator()
        toolbar.addWidget(self._build_theme_box())
        toolbar.addSeparator()
        toolbar.addWidget(self._build_search_box())

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

    def _build_theme_box(self) -> QComboBox:
        """The three-state theme switch of D-030 (跟随系统 / 浅色 / 深色)."""
        box = QComboBox(self)
        box.addItems([label for _, label in THEME_CHOICES])
        box.setFixedWidth(110)
        box.activated.connect(self._on_theme_activated)
        self._theme_box = box
        return box

    def _on_theme_activated(self) -> None:
        box = self._theme_box
        if box is None:
            return
        index = box.currentIndex()
        if 0 <= index < len(THEME_CHOICES):
            mode = THEME_CHOICES[index][0]
            theme = self.apply_theme(mode)
            self.statusBar().showMessage(f"主题：{box.currentText()}（{theme.value}）")

    def _build_search_box(self) -> QLineEdit:
        """The toolbar search box of V1.1 (T-019): Enter finds, Enter again finds the next."""
        box = QLineEdit(self)
        box.setPlaceholderText("搜索…（回车定位）")
        box.setClearButtonEnabled(True)
        box.setFixedWidth(190)
        box.returnPressed.connect(self._search_next)
        self._search_box = box
        return box

    def _reset_search(self) -> None:
        """Drop the hit list when another document loads: it described the previous one."""
        self._hits = ()
        self._hit_index = -1
        self._hit_query = ""

    def _search_next(self) -> None:
        """Search case-sensitively in every card's own text, then step through the hits.

        The query is re-run whenever it changes; pressing Enter again walks to the next hit and
        wraps around — the "find next" behaviour a toolbar box is expected to have. Locating
        goes through the same :meth:`_focus_card` as the outline and the TOC card.
        """
        box = self._search_box
        if box is None:  # pragma: no cover - built in __init__
            return
        query = box.text().strip()
        if not query:
            self.statusBar().showMessage("输入关键字后回车")
            return
        document = self.session.document
        if document is None:
            self.statusBar().showMessage("先打开一个 Markdown 文件")
            return
        if query != self._hit_query:
            self._hits = search_cards(document.tree, self.session.blocks, query)
            self._hit_index = -1
            self._hit_query = query
        if not self._hits:
            self.statusBar().showMessage(shorten(f"未找到：{query}"))
            return
        self._hit_index = (self._hit_index + 1) % len(self._hits)
        hit = self._hits[self._hit_index]
        if self._focus_card(hit.card_id):
            position = f"{self._hit_index + 1}/{len(self._hits)}"
            self.statusBar().showMessage(
                shorten(f"{query}：第 {position} 个命中（{hit.matches} 处）· 已定位 {hit.title}")
            )

    def _build_outline(self) -> None:
        """The dockable heading tree of V1.1 (T-020/T-032: a dockable, collapsible side panel).

        Entries come from the same slice as the TOC card (``BoardSession.toc``), so the panel
        and the card can never describe different documents, and a click goes through the same
        :meth:`_focus_card` path as a TOC line. Since T-032 the panel carries its own collapse
        control and the window a ``Ctrl+B`` shortcut; its visibility is deliberately *not*
        persisted (D-041), so every start begins with it open on the left.
        """
        tree = QTreeWidget(self)
        tree.setHeaderHidden(True)
        tree.setUniformRowHeights(True)
        tree.itemClicked.connect(self._on_outline_clicked)

        dock = QDockWidget("大纲", self)
        dock.setObjectName("outlineDock")
        dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        dock.setWidget(self._build_outline_panel(tree))
        dock.visibilityChanged.connect(self._on_outline_visibility_changed)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self._outline, self._outline_dock = tree, dock

        toggle = dock.toggleViewAction()
        toggle.setText("大纲")
        if self._toolbar is not None:
            self._toolbar.addSeparator()
            self._toolbar.addAction(toggle)

        shortcut = QAction(self)
        shortcut.setShortcut(QKeySequence(OUTLINE_SHORTCUT))
        shortcut.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        shortcut.setCheckable(True)
        shortcut.setChecked(True)
        shortcut.triggered.connect(self._toggle_outline)
        self.addAction(shortcut)
        self._outline_action = shortcut

    def _build_outline_panel(self, tree: QTreeWidget) -> QWidget:
        """The dock content: a collapse button row above the heading tree (T-032)."""
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        row = QHBoxLayout()
        row.setContentsMargins(4, 2, 4, 2)
        row.addStretch(1)
        collapse = QToolButton(panel)
        collapse.setObjectName("outlineCollapse")
        collapse.setText("收起")
        collapse.setToolTip(f"收起侧栏（{OUTLINE_SHORTCUT}）")
        collapse.clicked.connect(self._toggle_outline)
        row.addWidget(collapse)
        layout.addLayout(row)
        layout.addWidget(tree, 1)
        self._outline_collapse = collapse
        return panel

    def _toggle_outline(self) -> None:
        """Show or hide the outline sidebar; both the button and Ctrl+B land here (T-032).

        Hiding is not remembered on purpose (D-041): a restart starts with the panel open.
        """
        dock = self._outline_dock
        if dock is None:  # pragma: no cover - built in __init__
            return
        dock.setVisible(not dock.isVisible())

    def _on_outline_visibility_changed(self, visible: bool) -> None:
        """Report the state whichever way it changed: button, Ctrl+B, toolbar entry, close box."""
        self.statusBar().showMessage("侧栏已展开" if visible else "侧栏已收起")
        if self._outline_action is not None:
            self._outline_action.setChecked(visible)

    def _rebuild_outline(self) -> None:
        """Rebuild the tree for the loaded document; heading levels nest the rows."""
        tree = self._outline
        if tree is None:  # pragma: no cover - the dock exists before any document loads
            return
        tree.clear()
        open_levels: list[tuple[int, QTreeWidgetItem]] = []
        for entry in self.session.toc:
            node = QTreeWidgetItem([entry.label])
            node.setData(0, Qt.ItemDataRole.UserRole, entry.card_id)
            while open_levels and open_levels[-1][0] >= entry.level:
                open_levels.pop()
            if open_levels:
                open_levels[-1][1].addChild(node)
            else:
                tree.addTopLevelItem(node)
            open_levels.append((entry.level, node))
        tree.expandAll()

    def _on_outline_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        del column
        card_id = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(card_id, str):
            self._focus_card(card_id)

    def _focus_card(self, card_id: CardId) -> bool:
        """Unfold, center, highlight and report one card (FR-2.4 / F10).

        One implementation for every "go to this card" caller — TOC lines (T-021) and the
        outline panel (T-020) — so the two can never drift apart in behaviour.
        """
        unfolded = self.session.reveal(card_id)
        item = self._items.get(card_id)
        if item is None:  # pragma: no cover - callers pass ids from the current card tree
            return False
        self.scene.clearSelection()
        item.setSelected(True)
        self.view.centerOn(item.sceneBoundingRect().center())
        note = f"（已展开 {unfolded} 层折叠祖先）" if unfolded else ""
        self.statusBar().showMessage(shorten(f"已定位：{item.card.title}{note}"))
        return True

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

    def _place_overlay(self) -> None:
        """Pin the strip inside the board's bottom-right corner (T-035, D-044).

        The strip is a child of the *window*, so its position needs the central widget's
        **origin** as well as its size. Using the size alone (the pre-T-035 code) left it
        ``central.x()`` / ``central.y()`` px away from the corner — measured 280 px / 48 px
        with the sidebar open, against the 18 px the code and the spec both intended.
        """
        central = self.centralWidget()
        if central is None:  # pragma: no cover - set in __init__ and never cleared
            return
        size = self._overlay.sizeHint()
        self._overlay.resize(size)
        board = central.geometry()
        self._overlay.move(
            board.x() + board.width() - size.width() - OVERLAY_MARGIN,
            board.y() + board.height() - size.height() - OVERLAY_MARGIN,
        )

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Follow the *board's* resize, not only the window's (T-035).

        Collapsing or widening the sidebar changes the central widget's geometry without
        resizing the window, so ``resizeEvent`` alone would leave the strip behind.
        """
        if watched is self.view and event.type() == QEvent.Type.Resize:
            self._place_overlay()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._place_overlay()
        self.view.refresh_scene_rect()  # a screen of pannable canvas on every side (T-040)

    def _connect(self) -> None:
        self.session.document_loaded.connect(self._rebuild_items)
        self.session.document_loaded.connect(self._rebuild_outline)
        self.session.document_loaded.connect(self._reset_search)
        self.session.cards_changed.connect(self._apply_geometry)
        self.session.status.connect(self._show_status)
        self.session.failed.connect(self._show_failure)
        self.view.zoom_changed.connect(self._on_zoom_changed)
        for bar in (self.view.horizontalScrollBar(), self.view.verticalScrollBar()):
            bar.valueChanged.connect(self._on_viewport_scrolled)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._show_context_menu)
        # The board also resizes on its own (sidebar width), so the floating strip follows
        # the view and not just the window (T-035).
        self.view.installEventFilter(self)
        self._follow_the_system_scheme()

    def _on_viewport_scrolled(self) -> None:
        """Recompute the render queue once the scroll settles (T-031, NFR-3).

        Debounced like the zoom path: a drag of the scrollbar fires hundreds of value changes,
        and rebuilding the queue on each of them would thrash.
        """
        self._scroll_timer.start(SCROLL_QUEUE_DELAY_MS)

    # ------------------------------------------------------------------ documents

    @property
    def card_items(self) -> dict[CardId, CardItem]:
        """The scene items, keyed by card id (read-only view for tests and tools)."""
        return dict(self._items)

    @property
    def renderer_build_error(self) -> str:
        """Why the body renderer could not be built, or ``""`` when it was fine."""
        return self._renderer_error

    @property
    def overlay(self) -> QWidget:
        """The floating 刷新 / 全部还原 strip (read-only view for tests and tools, T-035)."""
        return self._overlay

    def open_path(self, path: Path) -> bool:
        opened = self.session.open(path)
        if opened:
            self.setWindowTitle(f"{path.name} — {PRODUCT_NAME}")
            self.view.fit_cards()
        return opened

    def _choose_file(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self, "打开 Markdown 文件", "", "Markdown (*.md *.markdown *.mdx);;所有文件 (*)"
        )
        if selected:
            self.open_path(Path(selected))

    def _new_window(self) -> None:
        """Open another window in its own process; windows stay independent (FR-6.1/6.2)."""
        from mcwr.interfaces.gui.app import spawn_new_window

        started = spawn_new_window(None, parent_pid=os.getpid())
        self.statusBar().showMessage(
            "new window started (independent session)" if started else "could not start a window"
        )

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

    def _show_status(self, message: str) -> None:
        """Status bar stays short (T-026 item 9); the full text is not lost, it is logged."""
        seed = self.session.path.name if self.session.path is not None else "mcwr"
        self.statusBar().showMessage(shorten(f"{seed}: {message}"))

    def _show_failure(self, message: str) -> None:
        logger().error("{}", message)
        self._show_status(f"错误：{message}")

    # -------------------------------------------------------------------- drawing

    def _rebuild_items(self) -> None:
        for item in self._items.values():
            if item.scene() is self.scene:  # a detached item may already belong elsewhere
                self.scene.removeItem(item)
        self._items.clear()
        document = self.session.document
        if document is None:
            return
        if self.session.over_limit:
            # One line per load, next to the status-bar notice (D-029): whoever reads the log
            # later must see that the missing formulas are a deliberate downgrade.
            logger().warning(
                "{}: {} cards exceed the {} limit; rich rendering is off, cards show source text",
                document.document.path.name,
                self.session.card_count,
                MAX_CARDS,
            )
        blocks = self.session.blocks
        self._toc = self.session.toc
        for card_id in document.tree.ordered_ids():
            card = document.tree.cards[card_id]
            layout = self.session.layouts.get(card_id)
            if layout is None:
                continue
            item = CardItem(
                card,
                blocks,
                layout,
                palette=self._palette,
                toc=self._toc,
                depth=len(document.tree.ancestors(card_id)),
            )
            item.moved.connect(self._on_item_moved)
            item.link_clicked.connect(self._on_link_clicked)
            self._items[card_id] = item
        self._reparent_items()
        self._apply_geometry(tuple(self._items))
        # The estimator only guesses; the documents exist now, so hand the real heights back
        # (T-049) and lay the board out again -- no card keeps phantom padding, none clips.
        self.session.adopt_measured_heights(
            {
                card_id: height
                for card_id, item in self._items.items()
                if (height := item.measured_body_height()) is not None
            }
        )
        self._queue_body_images()

    # ---------------------------------------------------------------- body images

    def _queue_body_images(self) -> None:
        """Schedule offscreen renders for the math / mermaid cards the user can see (D14, NFR-3).

        Rendering is deferred one card per event-loop turn so the board stays responsive and a
        first-time KaTeX/Mermaid render never blocks the window from appearing. Since T-031 the
        queue holds only what is *on screen* (plus half a screen of margin), nearest to the
        viewport centre first, so a thousand-card document costs what its viewport costs.
        """
        document = self.session.document
        if document is None or self.session.over_limit:
            # D-029/D-040: past the card limit the heavy path is skipped entirely — no queue,
            # no pending badges, and the math/mermaid cards keep the text drawn from their
            # source. This is also what keeps an over-limit document interactive.
            return
        bucket = self._current_bucket()
        theme = self._theme.value
        candidates = self._render_candidates_now()
        self._render_candidates = set(candidates)
        pending = [
            card_id for card_id in candidates if (card_id, bucket, theme) not in self._pixmaps
        ]
        self._release_offscreen_pixmaps()
        if not pending:
            return
        self._image_queue = pending
        for card_id in pending:
            item = self._items.get(card_id)
            if item is not None:
                item.set_pending(True)  # D-022 item 4: progress is visible while rendering
        self._image_timer.start(0)

    def _render_candidates_now(self) -> list[CardId]:
        """The cards worth rasterizing right now, nearest to the viewport centre first.

        A card qualifies when it needs a web render, is not hidden inside a folded ancestor,
        is big enough on screen (T-031's floor) and intersects the viewport plus half a screen
        of margin. Everything else stays in its text form, which is exactly NFR-3's "cards
        outside the viewport are not rendered or degrade to a placeholder".
        """
        document = self.session.document
        if document is None:  # pragma: no cover - callers check first
            return []
        area = self._render_area()
        zoom = self.view.zoom_percent() / 100.0
        centre = self.view.mapToScene(self.view.viewport().rect().center())
        candidates: list[tuple[float, CardId]] = []
        for card_id, card in document.tree.cards.items():
            item = self._items.get(card_id)
            if item is None or not needs_web_render(card) or self._is_hidden(card_id):
                continue
            if item.card_width * zoom < MIN_LEGIBLE_ON_SCREEN_WIDTH:
                continue
            bounds = item.sceneBoundingRect()
            if not area.intersects(bounds):
                continue
            offset = bounds.center() - centre
            candidates.append((offset.x() ** 2 + offset.y() ** 2, card_id))
        candidates.sort(key=lambda pair: pair[0])
        return [card_id for _, card_id in candidates]

    def _render_area(self) -> QRectF:
        """The visible scene rect grown by half a screen on each side (prefetch margin)."""
        visible = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        return visible.adjusted(
            -visible.width() / 2.0,
            -visible.height() / 2.0,
            visible.width() / 2.0,
            visible.height() / 2.0,
        )

    def _release_offscreen_pixmaps(self) -> None:
        """Keep the in-memory rasters bounded by dropping cards that scrolled away (T-031).

        Only rasters outside the render area are candidates, so a visible card never loses the
        image it is showing; the PNG itself stays in the on-disk cache (T-017), so scrolling
        back re-reads it instead of re-rendering.
        """
        if len(self._pixmaps) <= MAX_LIVE_PIXMAPS:
            return
        area = self._render_area()
        for key in list(self._pixmaps):
            if len(self._pixmaps) <= MAX_LIVE_PIXMAPS:
                return
            card_id = key[0]
            item = self._items.get(card_id)
            if item is not None and area.intersects(item.sceneBoundingRect()):
                continue
            del self._pixmaps[key]
            if item is not None and not any(stored[0] == card_id for stored in self._pixmaps):
                item.set_image(None)

    def _current_bucket(self) -> float:
        """The render bucket for the current zoom; falls back to a 0.5 step."""
        renderer = self._renderer
        scale = self.view.zoom_percent() / 100.0
        bucket_for = getattr(renderer, "bucket_for", None)
        if callable(bucket_for):
            return float(bucket_for(scale))
        return round(scale * 2) / 2

    def _render_next_body(self) -> None:
        """Render one queued card, then reschedule itself until the queue drains.

        A card that scrolled out of the render area while it waited is dropped instead of
        rasterized (T-031): the user cannot see it, and it may never be looked at.
        """
        if not self._image_queue:
            return
        document = self.session.document
        card_id = self._image_queue.pop(0)
        if document is None:
            return
        card = document.tree.cards.get(card_id)
        item = self._items.get(card_id)
        if card is None or item is None:
            self._image_timer.start(0)
            return
        if card_id not in self._render_candidates:
            item.set_pending(False)
            if self._image_queue:
                self._image_timer.start(0)
            return

        renderer = self._renderer
        if renderer is None:
            try:
                renderer = container.build_web_renderer()
            except Exception as exc:  # noqa: BLE001 - a broken bundle must not silently skip
                self._renderer_error = f"{type(exc).__name__}: {exc}"
                self.session.failed.emit(f"body rendering unavailable: {self._renderer_error}")
                return
            self._renderer = renderer
        theme = self._theme.value
        path = card_image(
            card,
            self.session.blocks,
            renderer=renderer,
            scale=self.view.zoom_percent() / 100.0,
            theme=theme,
        )
        if path is not None:
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                self._pixmaps[(card_id, self._current_bucket(), theme)] = pixmap
                item.set_image(pixmap)
        else:
            reason = getattr(renderer, "last_error", None) or "unknown reason"
            logger().error("card {} kept its text form: {}", card_id, reason)
            self._show_status(f"{card.kind} 卡渲染失败")
        item.set_pending(False)
        if self._image_queue:
            self._image_timer.start(0)

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
        # Parents first, always (E-028). A child's local position is computed against its parent's
        # current scene position *and* clamped against the parent's current height, so the parent
        # must already be placed. The incoming order cannot be trusted: the layout mapping is built
        # in post-order (a card is stored after its children), which used to leave the last
        # siblings of a re-stacked parent sitting on their old coordinates.
        wanted = set(card_ids)
        for card_id in document.tree.ordered_ids():
            if card_id not in wanted:
                continue
            item = self._items.get(card_id)
            layout = self.session.layouts.get(card_id)
            if item is None or layout is None:
                continue
            item.set_card_geometry(layout.width, layout.height)
            item.setZValue(float(layout.z))
            card = document.tree.cards.get(card_id)
            # A re-layout replaces CardLayout objects, so the item has to point at the current
            # one: its boundary clamp reads ``detached`` from here (E-026).
            item.layout_state = layout
            # A child inside its parent is frozen; free cards and parentless cards may be dragged
            # (T-043, D-050).
            item.set_movable(layout.detached or card is None or card.parent_id is None)
            parent_item = item.parentItem()
            offset = parent_item.scenePos() if parent_item is not None else QPointF(0.0, 0.0)
            item.setPos(QPointF(layout.x - offset.x(), layout.y - offset.y()))
            item.setVisible(not self._is_hidden(card_id))
        self.view.refresh_scene_rect()  # cards moved: keep the pannable margin (T-040)

    def _toggle_snap(self) -> None:
        """Turn grid snapping on or off (T-048, D-051); the state lives for this window only."""
        state = "on" if self.action_snap.isChecked() else "off"
        self.statusBar().showMessage(f"grid snap {state}")

    def _on_item_moved(self, item: object, x: float, y: float) -> None:
        if isinstance(item, CardItem):
            self.session.move_card(item.card.card_id, x, y, snap=self.action_snap.isChecked())
            layout = self.session.layouts[item.card.card_id]
            note = " (snapped to grid)" if (layout.x, layout.y) != (x, y) else ""
            self.statusBar().showMessage(
                f"moved {item.card.title!r} to ({layout.x:.0f}, {layout.y:.0f}){note}"
            )

    def _on_link_clicked(self, source: object, anchor: str) -> None:
        """Jump to the card a TOC line points at (FR-2.4, flow F10)."""
        label = source.card.title if isinstance(source, CardItem) else anchor
        target = resolve_anchor(self._toc, anchor)
        if target is None:
            self.statusBar().showMessage(shorten(f"{label}：目录项未找到对应标题卡"))
            return
        self._focus_card(target)

    def _on_zoom_changed(self, percent: float) -> None:
        if self._zoom_box is not None:
            self._zoom_box.setCurrentText(f"{percent:.0f}")
        self.session.set_viewport(
            percent / 100.0,
            float(self.view.horizontalScrollBar().value()),
            float(self.view.verticalScrollBar().value()),
        )
        self._zoom_timer.start(400)  # re-render only after the zoom settles (D14 buckets)

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
        if self.view.suppresses_context_menu():
            return  # a marquee selection owns the right button (D-052)
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
            any(layouts[child].detached for child in tree.descendants(card_id) if child in layouts)
        )
        reclaim.triggered.connect(lambda: self.session.reclaim(card_id))

        fold = menu.addAction("折叠 / 展开")
        fold.setEnabled(bool(tree.cards[card_id].child_ids))
        fold.triggered.connect(lambda: self.session.fold(card_id))


def _action(window: MainWindow, text: str, shortcut: str, slot: Callable[[], None]) -> QAction:
    action = QAction(text, window)
    action.setShortcut(QKeySequence(shortcut))
    action.triggered.connect(slot)
    return action


def _percent(text: str) -> float:
    try:
        return float(text.strip().rstrip("%"))
    except ValueError:
        return 100.0
