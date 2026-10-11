"""Card visuals: one QGraphicsItem per card, children parented to their card (D8).

Geometry comes from the domain (`CardLayout`, absolute whiteboard coordinates); this
module converts to Qt's local coordinates only when applying a layout, and converts
back on drop. Moving a card therefore moves its attached children for free.
"""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap, QTextDocument
from PySide6.QtWidgets import (
    QGraphicsObject,
    QGraphicsSceneMouseEvent,
    QStyle,
    QStyleOptionGraphicsItem,
    QWidget,
)

from mcwr.domain.enums import CardKind
from mcwr.domain.models import Block, Card, CardLayout

HEADER_HEIGHT = 34.0
PADDING = 12.0
RADIUS = 8.0
MIN_BODY_HEIGHT = 24.0

ACCENT: dict[CardKind, str] = {
    CardKind.BIG_SECTION: "#4a5568",
    CardKind.HEADING: "#2b6cb0",
    CardKind.CODE: "#2f855a",
    CardKind.TABLE: "#805ad5",
    CardKind.MATH_BLOCK: "#b7791f",
    CardKind.MERMAID: "#0987a0",
    CardKind.IMAGE: "#c05621",
    CardKind.TASK_LIST: "#6b46c1",
    CardKind.TOC: "#718096",
    CardKind.FALLBACK_TEXT: "#a0aec0",
}

KIND_GLYPH: dict[CardKind, str] = {
    CardKind.BIG_SECTION: "§",
    CardKind.HEADING: "H",
    CardKind.CODE: "</>",
    CardKind.TABLE: "▦",
    CardKind.MATH_BLOCK: "∑",
    CardKind.MERMAID: "◇",
    CardKind.IMAGE: "▣",
    CardKind.TASK_LIST: "☑",
    CardKind.TOC: "≡",
    CardKind.FALLBACK_TEXT: "¶",
}


class CardItem(QGraphicsObject):
    """Paints one card: frame, header with kind glyph, and its own (direct) content."""

    moved = Signal(object, float, float)
    """Emitted after a drag finishes: (item, whiteboard x, whiteboard y)."""

    def __init__(
        self,
        card: Card,
        blocks: Mapping[int, Block],
        layout: CardLayout,
        image: QPixmap | None = None,
    ) -> None:
        super().__init__()
        self.card = card
        self.layout_state = layout
        self._document = _build_document(card, blocks)
        self._image = image
        self._pending = False
        self._width = max(layout.width, 120.0)
        self._height = max(layout.height, HEADER_HEIGHT + MIN_BODY_HEIGHT)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setCacheMode(QGraphicsObject.CacheMode.DeviceCoordinateCache)

    # ------------------------------------------------------------------ geometry

    def boundingRect(self) -> QRectF:
        return QRectF(0.0, 0.0, self._width, self._height)

    def set_card_geometry(self, width: float, height: float) -> None:
        if (width, height) == (self._width, self._height):
            return
        self.prepareGeometryChange()
        self._width = max(width, 120.0)
        self._height = max(height, HEADER_HEIGHT + MIN_BODY_HEIGHT)

    @property
    def card_width(self) -> float:
        return self._width

    @property
    def card_height(self) -> float:
        return self._height

    def body_rect(self) -> QRectF:
        return QRectF(
            PADDING,
            HEADER_HEIGHT,
            max(self._width - 2 * PADDING, 1.0),
            max(self._height - HEADER_HEIGHT - PADDING, 1.0),
        )

    # ------------------------------------------------------------------- painting

    def set_image(self, image: QPixmap | None) -> None:
        """Show an offscreen-rendered body (math / mermaid), or fall back to the text.

        Rendering happens outside the paint path (decision D14), so the canvas only ever
        draws a static pixmap and stays smooth while the board is transformed.
        """
        self._image = image
        self.update()

    def set_pending(self, pending: bool) -> None:
        """Mark the card as "image on the way" so the user sees progress, not a stall.

        D-022 item 4 asks for an async render with a visible placeholder: the body keeps
        its text form while the raster is being produced, and the header shows a small
        badge until the attempt finishes (success or documented fallback).
        """
        if pending == self._pending:
            return
        self._pending = pending
        self.update()

    @property
    def is_pending(self) -> bool:
        return self._pending

    @property
    def has_image(self) -> bool:
        return self._image is not None and not self._image.isNull()

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        del widget
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        accent = QColor(ACCENT.get(self.card.kind, "#718096"))
        frame = QRectF(0.5, 0.5, self._width - 1.0, self._height - 1.0)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.drawRoundedRect(frame, RADIUS, RADIUS)

        header = QRectF(frame.left(), frame.top(), frame.width(), HEADER_HEIGHT)
        painter.setBrush(QBrush(accent.lighter(190)))
        painter.drawRoundedRect(header, RADIUS, RADIUS)
        painter.drawRect(QRectF(header.left(), header.bottom() - RADIUS, header.width(), RADIUS))

        painter.setPen(QPen(accent.darker(140)))
        painter.drawLine(
            QPointF(frame.left(), header.bottom()), QPointF(frame.right(), header.bottom())
        )
        _draw_header_text(painter, header, self.card)

        painter.save()
        painter.setClipRect(self.body_rect())
        if self.has_image and self._image is not None:
            _draw_body_image(painter, self.body_rect(), self._image)
        else:
            painter.translate(self.body_rect().topLeft())
            self._document.setTextWidth(self.body_rect().width())
            self._document.drawContents(
                painter, QRectF(0, 0, self.body_rect().width(), 1e6)
            )
        painter.restore()

        border = QColor("#2d3748") if selected else accent
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(border, 2.5 if selected else 1.0))
        painter.drawRoundedRect(frame, RADIUS, RADIUS)

        if self._pending and not self.has_image:
            _draw_pending_badge(painter, header)

    # ----------------------------------------------------------------- item hooks

    def itemChange(self, change: QGraphicsObject.GraphicsItemChange, value: object) -> object:
        """Keep an attached child inside its parent (FR-3.4, acceptance 4).

        Qt happily moves a child item outside its parent's rectangle; the spec forbids
        that until the card is explicitly detached, so the position is clamped here.
        Free cards (``detached``) and top-level cards move without constraint.
        """
        inside = change == QGraphicsObject.GraphicsItemChange.ItemPositionChange
        parent = self.parentItem()
        point = value
        if (
            inside
            and not self.layout_state.detached
            and isinstance(parent, CardItem)
            and isinstance(point, QPointF)
        ):
            max_x = max(parent.card_width - self._width, 0.0)
            max_y = max(parent.card_height - self._height, 0.0)
            return QPointF(min(max(point.x(), 0.0), max_x), min(max(point.y(), 0.0), max_y))
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        position = self.scenePos()
        self.moved.emit(self, position.x(), position.y())


def _draw_pending_badge(painter: QPainter, header: QRectF) -> None:
    """A small "rendering…" pill on the right of the header (D-022 item 4)."""
    font = QFont("Segoe UI", 8)
    painter.setFont(font)
    text = "渲染中…"
    width = painter.fontMetrics().horizontalAdvance(text) + 12.0
    pill = QRectF(header.right() - width - 8.0, header.top() + 7.0, width, header.height() - 14.0)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor("#ffffff")))
    painter.drawRoundedRect(pill, pill.height() / 2.0, pill.height() / 2.0)
    painter.setPen(QPen(QColor("#4a5568")))
    painter.drawText(pill, int(Qt.AlignmentFlag.AlignCenter), text)


def _draw_body_image(painter: QPainter, body: QRectF, image: QPixmap) -> None:
    """Draw the rendered body scaled to fit the card, keeping its aspect ratio."""
    scaled = image.scaled(
        body.size().toSize(),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    painter.drawPixmap(int(body.left()), int(body.top()), scaled)


def _build_document(card: Card, blocks: Mapping[int, Block]) -> QTextDocument:
    """Render this card's own blocks (never its children's) as Markdown text."""
    parts: list[str] = []
    for index in card.own_block_indexes:
        block = blocks.get(index)
        if block is None:
            continue
        if card.kind is CardKind.HEADING and block.index == card.block_index:
            continue  # a heading's text already lives in the header bar
        text = block.raw_text.strip()
        if text:
            parts.append(text)
    document = QTextDocument()
    document.setDefaultFont(QFont("Segoe UI", 10))
    document.setMarkdown("\n\n".join(parts))
    return document


def _draw_header_text(painter: QPainter, header: QRectF, card: Card) -> None:
    glyph = KIND_GLYPH.get(card.kind, "•")
    painter.setPen(QPen(QColor("#1a202c")))
    font = QFont("Segoe UI", 10)
    font.setBold(True)
    painter.setFont(font)
    glyph_rect = QRectF(header.left() + 8.0, header.top(), 30.0, header.height())
    painter.drawText(glyph_rect, int(Qt.AlignmentFlag.AlignVCenter), glyph)
    title_rect = QRectF(
        glyph_rect.right() + 4.0, header.top(), header.width() - 50.0, header.height()
    )
    title = f"{card.title}  ·  {card.kind}" if card.kind is not CardKind.HEADING else card.title
    elided = painter.fontMetrics().elidedText(
        title, Qt.TextElideMode.ElideRight, int(title_rect.width())
    )
    painter.drawText(
        title_rect,
        int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
        elided,
    )
