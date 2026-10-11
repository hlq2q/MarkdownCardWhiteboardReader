"""Whiteboard canvas: scene + view with cursor-anchored zoom, pan and fit (FR-3.2/3.3)."""

from __future__ import annotations

from PySide6.QtCore import QLineF, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QTransform, QWheelEvent
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QWidget

from mcwr.domain.models import Viewport
from mcwr.interfaces.gui.theme import GRID_ALPHA, GRID_STEP, LIGHT, Palette


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
        super().drawBackground(painter, rect)
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

    # -------------------------------------------------------------------- events

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta:
            self.zoom_by(1.15 ** (delta / 120.0))
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._panning and event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.viewport().unsetCursor()
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
