"""Whiteboard canvas: scene + view with cursor-anchored zoom, pan and fit (FR-3.2/3.3)."""

from __future__ import annotations

from typing import Final

from PySide6.QtCore import QLineF, QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPen,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QRubberBand, QWidget

from mcwr.domain.models import Viewport
from mcwr.interfaces.gui.card_item import CardItem
from mcwr.interfaces.gui.theme import GRID_ALPHA, GRID_STEP, LIGHT, Palette

MIN_GRID_DEVICE_STEP: Final[float] = 8.0

PAN_MARGIN: Final[float] = 600.0
"""Empty canvas kept around the cards so the middle-button pan has somewhere to go (T-040)."""
"""Grid spacing (device px) below which the grid is not drawn at all (T-033).

A different quantity from ``theme.MIN_LEGIBLE_ON_SCREEN_WIDTH`` on purpose: that one is a card
width in logical px, this one the on-screen distance between two grid lines. With
``GRID_STEP = 40`` scene units the grid is skipped at 20 % zoom and below — the whole overview
range, where a 4 px mesh reads as a tint and costs more than everything else in the frame —
while every zoom from 25 % up keeps exactly the grid it had before.
"""


class BoardScene(QGraphicsScene):
    """The whiteboard surface: a themed canvas with a faint grid for orientation."""

    def __init__(self, parent: QWidget | None = None, palette: Palette = LIGHT) -> None:
        super().__init__(parent)
        self._palette = palette
        self._grid_pen = QPen(_grid_colour(palette), 0.0)
        self.setBackgroundBrush(QColor(palette.board_bg))

    @property
    def visual_palette(self) -> Palette:
        """The palette the board paints with (read-only view for tests).

        Not named ``palette``: ``QGraphicsScene.palette()`` is Qt's ``QPalette`` accessor.
        """
        return self._palette

    def set_palette(self, palette: Palette) -> None:
        """Repaint the canvas and its grid in another theme (T-024 ③); moves nothing."""
        if palette.theme is self._palette.theme:
            return
        self._palette = palette
        self._grid_pen = QPen(_grid_colour(palette), 0.0)
        self.setBackgroundBrush(QColor(palette.board_bg))
        self.update()

    def drawBackground(self, painter: QPainter, rect: QRectF | QRect) -> None:
        """Fill the canvas and draw the orientation grid — unless the grid is below the floor.

        The exposed ``rect`` arrives in *scene* coordinates, so at a small zoom it is enormous
        (at 10 % a 1400x900 window exposes ~11240x8460 units) and a 24-unit grid means hundreds
        of scene-long antialiased lines. Measured on a 1000-card board: that background cost
        ~40 ms of a 46 ms frame — more than every visible card together (T-033, and the reason
        the card-painting hypothesis was wrong). Below ``MIN_GRID_DEVICE_STEP`` the grid is a
        flat tint nobody can read, so it is skipped; the fill still happens, and the bounding
        rule also caps the line count at viewport_px / floor.
        """
        super().drawBackground(painter, rect)
        if GRID_STEP * abs(painter.transform().m11()) < MIN_GRID_DEVICE_STEP:
            return
        rect = QRectF(rect)
        left = rect.left() - (rect.left() % GRID_STEP)
        top = rect.top() - (rect.top() % GRID_STEP)
        painter.setPen(self._grid_pen)
        lines: list[QLineF] = []
        x = left
        while x < rect.right():
            lines.append(QLineF(x, rect.top(), x, rect.bottom()))
            x += GRID_STEP
        y = top
        while y < rect.bottom():
            lines.append(QLineF(rect.left(), y, rect.right(), y))
            y += GRID_STEP
        painter.drawLines(lines)


def _grid_colour(palette: Palette) -> QColor:
    """Spec §4: the grid is ``divider`` at 40% opacity, drawn over the board fill."""
    colour = QColor(palette.divider)
    colour.setAlpha(GRID_ALPHA)
    return colour


class BoardView(QGraphicsView):
    """Zoomable, pannable view. Zoom is one canvas transform (decision D7)."""

    zoom_changed = Signal(float)
    card_activated = Signal(object)
    cards_moved = Signal(list, float, float)
    """Emitted when a group or card drag ends: the ids plus the scene delta (T-051)."""

    scale_requested = Signal(object, float)
    """Ctrl + wheel over a card: the card id and the factor (T-057)."""

    scale_reset_requested = Signal(object)
    """Ctrl + right double-click on a card: give it its natural size back (T-057)."""
    """Emitted when a drag ends: the card ids plus the scene delta (T-051)."""

    def __init__(self, scene: BoardScene, parent: QWidget | None = None) -> None:
        super().__init__(scene, parent)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self._panning = False
        self._pan_origin = QPointF()
        self._view_drag: tuple[CardItem, QPointF, QPointF] | None = None
        self._marquee_selection = False
        self._marquee_dragged = False
        self._marquee_origin: QPointF | None = None
        self._marquee_band = QRubberBand(QRubberBand.Shape.Rectangle, self.viewport())
        self._group_drag: tuple[list[CardItem], QPointF, list[QPointF]] | None = None
        self._menu_suppressed = False
        self._text_item: CardItem | None = None
        self._text_drag = False

    # ----------------------------------------------------------------------- zoom

    def zoom_percent(self) -> float:
        return self.transform().m11() * 100.0

    def set_zoom(self, percent: float) -> None:
        """Apply an absolute zoom percentage, clamped to the domain bounds."""
        target = _clamp(percent / 100.0)
        self.setTransform(QTransform.fromScale(target, target))
        self.zoom_changed.emit(self.zoom_percent())

    def zoom_by(self, factor: float) -> None:
        current = self.transform().m11()
        target = _clamp(current * factor)
        if abs(target - current) < 1e-9:
            return
        ratio = target / current
        self.scale(ratio, ratio)
        self.zoom_changed.emit(self.zoom_percent())

    def fit_cards(self, margin: float = 40.0) -> None:
        """Frame the whole board (acceptance 9's "fit view"), staying inside the bounds."""
        bounds = self.scene().itemsBoundingRect().adjusted(-margin, -margin, margin, margin)
        if bounds.isEmpty():
            return
        self.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)
        fitted = self.transform().m11()
        if fitted > Viewport.MAX_SCALE or fitted < Viewport.MIN_SCALE:
            self.set_zoom(min(max(fitted, Viewport.MIN_SCALE), Viewport.MAX_SCALE) * 100.0)
        else:
            self.zoom_changed.emit(self.zoom_percent())

    def refresh_scene_rect(self) -> None:
        """Keep one screen of empty canvas around the cards so the view can pan (T-040).

        ``fit_cards`` frames ``itemsBoundingRect`` and therefore ignores this margin; only the
        scroll bars grow, which is what gives the middle-button pan somewhere to go sideways on
        a document narrower than the window.
        """
        scene = self.scene()
        step_x = max(float(self.viewport().width()), PAN_MARGIN)
        step_y = max(float(self.viewport().height()), PAN_MARGIN)
        bounds = scene.itemsBoundingRect()
        if bounds.isEmpty():
            bounds = QRectF(0.0, 0.0, 0.0, 0.0)
        self.setSceneRect(bounds.adjusted(-step_x, -step_y, step_x, step_y))

    # -------------------------------------------------------------------- events

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Ctrl + wheel over a card scales that card (T-057); a plain wheel keeps zooming.
            card = self.top_card_at(self.mapToScene(event.position().toPoint()))
            if card is not None:
                self.scale_requested.emit(card.card.card_id, 1.1 ** (delta / 120.0))
                event.accept()
                return
        if delta:
            self.zoom_by(1.15 ** (delta / 120.0))
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Start whichever gesture the press belongs to: pan, marquee, group move, text, or drag.

        Qt's own delivery skips a card when its *title bar* is pressed and hands the press to
        whatever is behind it (measured, E-027), so the title bar is taken over here. A press in the
        body belongs to the card's text (T-063): dragging selects, Ctrl+C copies, and a card is
        moved by its title bar.
        """
        if event.button() == Qt.MouseButton.RightButton:
            # The right button starts a marquee; the menu stays away while it is up (D-052). A plain
            # right press means the user wants the menu again, so drop an earlier veto.
            if not event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._menu_suppressed = False
            self._marquee_origin = event.position()
            self._marquee_dragged = False
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._marquee_selection = False  # a plain left press ends the marquee state
            self._menu_suppressed = False
            scene_point = self.mapToScene(event.position().toPoint())
            selected = [
                item
                for item in (self.scene().selectedItems() if self.scene() is not None else [])
                if isinstance(item, CardItem) and item.is_movable
            ]
            pressed = self.top_card_at(scene_point)
            if pressed is not None and pressed in selected and len(selected) > 1:
                # Pressing inside the selection moves all of it (D-052).
                for item in selected:
                    item.begin_view_drag(item.scenePos())
                self._group_drag = (
                    selected,
                    event.position(),
                    [item.scenePos() for item in selected],
                )
                event.accept()
                return
            if pressed is not None and not pressed.is_in_header(scene_point):
                if pressed.anchor_at_scene(scene_point):
                    super().mousePressEvent(event)  # a link keeps the document's own handling
                    return
                if self._begin_text_selection(pressed, scene_point):
                    event.accept()
                    return
            if pressed is not None and pressed.is_in_header(scene_point):
                self._take_over_press(pressed, event)
                return
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_origin = event.position()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)
        scene = self.scene()
        card = self.item_at(event.position().toPoint())
        if card is None or not card.is_movable or scene is None:
            return
        if scene.mouseGrabberItem() is card:
            return  # Qt grabbed it: its own drag (and its own release handler) is in charge
        self._take_over_press(card, event)

    def _take_over_press(self, card: CardItem, event: QMouseEvent) -> None:
        """Select ``card`` and drag it here; the card behind it must not move (E-027)."""
        scene = self.scene()
        if scene is not None:
            scene.clearSelection()
        card.setSelected(True)
        if card.is_movable:
            card.begin_view_drag(card.scenePos())
            self._view_drag = (card, event.position(), card.scenePos())
        event.accept()

    def item_at(self, point: QPoint) -> CardItem | None:
        """The card under ``point`` (viewport coordinates), if there is one."""
        item = self.itemAt(point)
        return item if isinstance(item, CardItem) else None

    def top_card_at(self, scene_point: QPointF) -> CardItem | None:
        """The topmost card whose box contains ``scene_point`` (E-027/T-051).

        A rectangle test, not ``itemAt``: Qt's own delivery skips a card when its title bar is
        pressed and hands the press to whatever is behind it, and the same skip applies here.
        """
        scene = self.scene()
        assert scene is not None, "the board always has a scene"
        found: CardItem | None = None
        for item in scene.items():
            if not isinstance(item, CardItem) or not item.sceneBoundingRect().contains(scene_point):
                continue
            if found is None or (item.zValue(), -item.sceneBoundingRect().width()) > (
                found.zValue(),
                -found.sceneBoundingRect().width(),
            ):
                found = item  # same depth: the innermost (smallest) card is the one being grabbed
        return found

    def copy_selection(self) -> bool:
        """Copy the card's text selection to the clipboard; False when there is none (T-063)."""
        if self._text_item is None or not self._text_item.has_selection():
            return False
        QGuiApplication.clipboard().setText(self._text_item.selected_text())
        return True

    def _begin_text_selection(self, card: CardItem, scene_point: QPointF) -> bool:
        """Give the press to the card's text instead of moving the card (T-063)."""
        if self._text_item is not None and self._text_item is not card:
            self._text_item.clear_selection()
        self._text_item = None
        if not card.start_selection(scene_point):
            return False
        self._text_item = card
        self._text_drag = True
        return True

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Drive the active gesture, or pan the viewport with the middle button (T-037)."""
        if not event.buttons():
            self._update_cursor(event.position())
        if self._text_drag and event.buttons() & Qt.MouseButton.LeftButton:
            if self._text_item is not None:
                self._text_item.extend_selection(self.mapToScene(event.position().toPoint()))
            event.accept()
            return
        if self._group_drag is not None:
            items, origin, positions = self._group_drag
            scale = self.transform().m11() or 1.0  # the board only ever scales, never rotates
            delta = (event.position() - origin) / scale
            for item, start in zip(items, positions, strict=True):
                item.setPos(start + delta)
            event.accept()
            return
        if self._marquee_origin is not None and event.buttons() & Qt.MouseButton.RightButton:
            delta = event.position() - self._marquee_origin
            if not self._marquee_dragged and (abs(delta.x()) > 4.0 or abs(delta.y()) > 4.0):
                self._marquee_dragged = True
                self._marquee_band.show()
            if self._marquee_dragged:
                self._marquee_band.setGeometry(
                    QRect(self._marquee_origin.toPoint(), event.position().toPoint()).normalized()
                )
                event.accept()
                return
        if self._view_drag is not None:
            card, origin, card_origin = self._view_drag
            scale = self.transform().m11() or 1.0  # the board only ever scales, never rotates
            delta = event.position() - origin
            card.setPos(card_origin + QPointF(delta.x() / scale, delta.y() / scale))
            event.accept()
            return
        if not self._panning:
            super().mouseMoveEvent(event)
            return
        delta = event.position() - self._pan_origin
        step = QPointF(float(int(delta.x())), float(int(delta.y())))
        self._pan_origin += step
        for bar, amount in (
            (self.horizontalScrollBar(), step.x()),
            (self.verticalScrollBar(), step.y()),
        ):
            bar.setValue(bar.value() - int(amount))
        event.accept()

    def _update_cursor(self, position: QPointF) -> None:
        """Show an I-beam over card text, the arrow anywhere else (T-065)."""
        scene_point = self.mapToScene(position.toPoint())
        card = self.top_card_at(scene_point)
        over_text = (
            card is not None
            and not card.is_in_header(scene_point)
            and card.has_text_at(scene_point)
        )
        if over_text:
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        else:
            self.viewport().unsetCursor()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Ctrl+C copies the card's text selection (T-063)."""
        if event.matches(QKeySequence.StandardKey.Copy) and self.copy_selection():
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Ctrl + right double-click gives a scaled card its natural size back (T-057).

        That gesture owns the right button, so the context menu stays away for it. Every other right
        double click is left completely alone: a quick second right click must not scroll the board
        out from under the user (that was the card jumping to the window edge). Only a left
        double click activates a card, and it does not move the view either.
        """
        if event.button() == Qt.MouseButton.RightButton:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                card = self.top_card_at(self.mapToScene(event.position().toPoint()))
                self._menu_suppressed = True
                if card is not None:
                    self.scale_reset_requested.emit(card.card.card_id)
                event.accept()
                return
            super().mouseDoubleClickEvent(event)
            return
        super().mouseDoubleClickEvent(event)
        item = self.top_card_at(self.mapToScene(event.position().toPoint()))
        if item is not None:
            self.card_activated.emit(item)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Finish the gesture the press started."""
        if self._text_drag and event.button() == Qt.MouseButton.LeftButton:
            self._text_drag = False  # the drag ends, the selection stays (T-063)
            event.accept()
            return
        if self._group_drag is not None and event.button() == Qt.MouseButton.LeftButton:
            items, origin, positions = self._group_drag
            self._group_drag = None
            scale = self.transform().m11() or 1.0
            delta = (event.position() - origin) / scale
            for item in items:
                item.end_view_drag(silent=True)
            # One report for the whole selection: the session moves every layout at once and snaps
            # the group as a whole (edges first, then the grid, D-052).
            self.cards_moved.emit([item.card.card_id for item in items], delta.x(), delta.y())
            event.accept()
            return
        if self._marquee_origin is not None and event.button() == Qt.MouseButton.RightButton:
            self._marquee_origin = None
            self._marquee_band.hide()
            if self._marquee_dragged:
                self._select_in_band()
            self._marquee_dragged = False
            event.accept()
            return
        if self._view_drag is not None and event.button() == Qt.MouseButton.LeftButton:
            card, origin, card_origin = self._view_drag
            self._view_drag = None
            card.end_view_drag()
            # The card's own item_moved signal already recorded the new position, so nothing else
            # may apply the delta again (that double-counted every drag).
            event.accept()
            return
        if self._panning and event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.viewport().unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def suppresses_context_menu(self) -> bool:
        """True while a marquee selection is up, so it never opens the card menu (D-052)."""
        return self._marquee_selection or self._marquee_dragged or self._menu_suppressed

    def vetoes_context_menu(self, modifiers: Qt.KeyboardModifier) -> bool:
        """Whether a context-menu request must be dropped (T-051/T-057).

        Two owners of the right button: a marquee selection (D-052), and Ctrl -- half of the
        size-reset gesture, so no menu may appear between the two clicks of a double-click.
        """
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            return True
        return self.suppresses_context_menu()

    def _select_in_band(self) -> None:
        """Select every *detached* card the band touches (D-052: frozen children stay out)."""
        scene = self.scene()
        assert scene is not None, "the band only exists on a scene"
        band = self.mapToScene(self._marquee_band.geometry()).boundingRect()
        scene.clearSelection()
        picked = 0
        for item in scene.items():
            if not isinstance(item, CardItem) or not item.layout_state.detached:
                continue  # D-052: only a card the user pulled out joins a marquee selection
            if item.sceneBoundingRect().intersects(band):
                item.setSelected(True)
                picked += 1
        self._marquee_selection = picked > 0


def _clamp(scale: float) -> float:
    return min(max(scale, Viewport.MIN_SCALE), Viewport.MAX_SCALE)
