"""Whiteboard canvas: scene + view with cursor-anchored zoom, pan and fit (FR-3.2/3.3)."""

from __future__ import annotations

from typing import Final

from PySide6.QtCore import QLineF, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QTransform, QWheelEvent
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QWidget

from mcwr.domain.models import Viewport
from mcwr.interfaces.gui.card_item import CardItem
from mcwr.interfaces.gui.theme import GRID_ALPHA, GRID_STEP, LIGHT, Palette

MIN_GRID_DEVICE_STEP: Final[float] = 8.0
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
        if delta:
            self.zoom_by(1.15 ** (delta / 120.0))
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """The middle button starts a 1:1 pan, and a movable card is grabbed anywhere on it.

        Qt's own ``ScrollHandDrag`` pans only while the *left* button is held, so the earlier
        middle-button branch — which merely switched the drag mode and the cursor — moved nothing
        at all. The press is consumed here: panning must neither select nor move a card, and the
        left button keeps its rubber-band selection untouched.

        Card presses are checked here because Qt's delivery skips a card when its *title bar* is
        pressed and hands the press to whatever is behind it (measured, E-027), which used to drag
        the whole section card instead of the card that was grabbed. A movable card under the
        cursor is therefore driven by the view when the scene did not grab it, and a frozen card
        under the cursor consumes the press itself (title bars have no links, so nothing is lost).
        """
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_origin = event.position()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        scene = self.scene()
        card = self.item_at(event.position().toPoint())
        if (
            card is not None
            and not card.is_movable
            and card.is_in_header(self.mapToScene(event.position().toPoint()))
        ):
            scene.clearSelection()
            card.setSelected(True)
            event.accept()
            return
        super().mousePressEvent(event)
        if card is None or not card.is_movable or scene is None:
            return
        if scene.mouseGrabberItem() is card:
            return  # Qt grabbed it: its own drag (and its own release handler) is in charge
        scene.clearSelection()
        card.setSelected(True)
        card.begin_view_drag(card.scenePos())
        self._view_drag = (card, event.position(), card.scenePos())
        event.accept()

    def item_at(self, point: QPoint) -> CardItem | None:
        """The card under ``point`` (viewport coordinates), if there is one."""
        item = self.itemAt(point)
        return item if isinstance(item, CardItem) else None

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Move the viewport with the cursor while the middle button is held (T-037).

        Only the integer part of the motion is applied and the remainder stays in the origin,
        so the view never drifts away from the cursor across a long drag.
        """
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

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._view_drag is not None and event.button() == Qt.MouseButton.LeftButton:
            card, _, _ = self._view_drag
            self._view_drag = None
            card.end_view_drag()
            event.accept()
            return
        if self._panning and event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.viewport().unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        super().mouseDoubleClickEvent(event)
        item = self.itemAt(event.position().toPoint())
        if item is not None:
            self.centerOn(QPointF(item.scenePos()))
            self.card_activated.emit(item)


def _clamp(scale: float) -> float:
    return min(max(scale, Viewport.MIN_SCALE), Viewport.MAX_SCALE)
