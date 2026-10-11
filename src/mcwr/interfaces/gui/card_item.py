"""Card visuals: one QGraphicsItem per card, children parented to their card (D8).

Geometry comes from the domain (`CardLayout`, absolute whiteboard coordinates); this
module converts to Qt's local coordinates only when applying a layout, and converts
back on drop. Moving a card therefore moves its attached children for free.

Every colour, font size and metric comes from :mod:`mcwr.interfaces.gui.theme`, which
implements ``docs/visual-spec.md`` — there is no literal colour in this file. A theme
switch calls :meth:`CardItem.set_palette`, which re-styles the card's own text document and
repaints: it never rebuilds the item and never touches a ``CardLayout`` (T-024 acceptance ③).
"""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPen,
    QPixmap,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QGraphicsObject,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent,
    QStyle,
    QStyleOptionGraphicsItem,
    QWidget,
)

from mcwr.domain.enums import CardKind
from mcwr.domain.models import Block, Card, CardLayout
from mcwr.interfaces.gui.theme import (
    BORDER_WIDTH,
    CARD_RADIUS,
    CODE_FONT,
    CODE_FONT_FALLBACK,
    FONT_PX,
    HEADER_HEIGHT,
    LIGHT,
    MIN_BODY_HEIGHT,
    PADDING,
    SELECTED_WIDTH,
    SHADOW_RGBA,
    UI_FONT,
    UI_FONT_FALLBACK,
    Palette,
    card_fill,
    points,
    uses_shadow,
)

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
"""Card type is carried by a glyph, never by colour alone (visual spec §6)."""


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
        palette: Palette = LIGHT,
    ) -> None:
        super().__init__()
        self.card = card
        self.layout_state = layout
        self._blocks = blocks
        self._palette = palette
        self._document = _build_document(card, blocks, palette)
        self._image = image
        self._pending = False
        self._hovered = False
        self._dragging = False
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

    @property
    def visual_palette(self) -> Palette:
        """The palette this item currently paints with (read-only view for tests)."""
        return self._palette

    def body_rect(self) -> QRectF:
        return QRectF(
            PADDING,
            HEADER_HEIGHT,
            max(self._width - 2 * PADDING, 1.0),
            max(self._height - HEADER_HEIGHT - PADDING, 1.0),
        )

    # ------------------------------------------------------------------- painting

    def set_palette(self, palette: Palette) -> None:
        """Switch this card's colours for a new theme (T-024 ③).

        Only the drawing changes: the card's text document is re-styled (fonts and code
        colours are baked into it) and the item repaints. No geometry, no layout field and
        no card identity is touched, and the board is never rebuilt.
        """
        if palette.theme is self._palette.theme:
            return
        self._palette = palette
        self._document = _build_document(self.card, self._blocks, palette)
        self.update()

    def set_image(self, image: QPixmap | None) -> None:
        """Show an offscreen-rendered body (math / mermaid), or fall back to the text.

        Rendering happens outside the paint path (decision D14), so the canvas only ever
        draws a static pixmap and stays smooth while the board is transformed. The image is
        theme-specific as well (visual spec §5), so a switch clears it and re-queues.
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
        palette = self._palette
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        fill = QColor(self._fill(palette))
        frame = QRectF(
            BORDER_WIDTH / 2.0,
            BORDER_WIDTH / 2.0,
            self._width - BORDER_WIDTH,
            self._height - BORDER_WIDTH,
        )

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        if uses_shadow(palette.theme):
            painter.setBrush(QBrush(QColor(*SHADOW_RGBA)))
            painter.drawRoundedRect(frame.translated(0.0, 1.0), CARD_RADIUS, CARD_RADIUS)

        painter.setBrush(QBrush(fill))
        painter.drawRoundedRect(frame, CARD_RADIUS, CARD_RADIUS)

        header = QRectF(frame.left(), frame.top(), frame.width(), HEADER_HEIGHT)
        painter.setPen(QPen(QColor(palette.border), BORDER_WIDTH))
        painter.drawLine(
            QPointF(frame.left(), header.bottom()), QPointF(frame.right(), header.bottom())
        )
        _draw_header_text(painter, header, self.card, palette)

        painter.save()
        painter.setClipRect(self.body_rect())
        if self.has_image and self._image is not None:
            _draw_body_image(painter, self.body_rect(), self._image)
        else:
            painter.translate(self.body_rect().topLeft())
            painter.setPen(QPen(QColor(palette.text_primary)))
            self._document.setTextWidth(self.body_rect().width())
            self._document.drawContents(
                painter, QRectF(0, 0, self.body_rect().width(), 1e6)
            )
        painter.restore()

        # Selection is a thicker border *and* another colour, never colour alone (§6).
        edge = QColor(palette.selected) if selected else QColor(palette.card_edge)
        width = SELECTED_WIDTH if selected else BORDER_WIDTH
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(edge, width))
        painter.drawRoundedRect(frame, CARD_RADIUS, CARD_RADIUS)

        if self._pending and not self.has_image:
            _draw_pending_badge(painter, header, palette)

    def _fill(self, palette: Palette) -> str:
        """Dragging wins over hovering, hovering over the kind's own fill (spec §4)."""
        if self._dragging:
            return palette.drag
        if self._hovered:
            return palette.hover
        return card_fill(palette, self.card.kind)

    # ----------------------------------------------------------------- item hooks

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

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

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if self._dragging:
            self._dragging = False
            self.update()
        position = self.scenePos()
        self.moved.emit(self, position.x(), position.y())


def _font(family: str, px: float, *, bold: bool = False, tracking_px: float = 0.0) -> QFont:
    """A font at one of the spec's pixel sizes, with its Windows fallback family list."""
    font = QFont(family)
    fallback = CODE_FONT_FALLBACK if family == CODE_FONT else UI_FONT_FALLBACK
    font.setFamilies([family, fallback])
    font.setPointSizeF(points(px))
    if bold:
        font.setWeight(QFont.Weight.DemiBold)
    if tracking_px:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, tracking_px)
    return font


def _stylesheet(palette: Palette) -> str:
    """The one place where the card's text document meets the palette (spec §5)."""
    return (
        f"a {{ color: {palette.link}; }} "
        f"code, pre {{ background-color: {palette.code_bg}; color: {palette.text_primary}; }} "
        f"h1, h2, h3, h4, h5, h6 {{ color: {palette.text_primary}; }} "
        f"th, td {{ color: {palette.text_primary}; }}"
    )


def _draw_pending_badge(painter: QPainter, header: QRectF, palette: Palette) -> None:
    """A small "rendering…" pill on the right of the header (D-022 item 4)."""
    painter.setFont(_font(UI_FONT, FONT_PX["control"], bold=True))
    text = "渲染中…"
    width = painter.fontMetrics().horizontalAdvance(text) + 12.0
    pill = QRectF(header.right() - width - 8.0, header.top() + 7.0, width, header.height() - 14.0)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor(palette.card_bg)))
    painter.drawRoundedRect(pill, pill.height() / 2.0, pill.height() / 2.0)
    painter.setPen(QPen(QColor(palette.text_secondary)))
    painter.drawText(pill, int(Qt.AlignmentFlag.AlignCenter), text)


def _draw_body_image(painter: QPainter, body: QRectF, image: QPixmap) -> None:
    """Draw the rendered body scaled to fit the card, keeping its aspect ratio."""
    scaled = image.scaled(
        body.size().toSize(),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    painter.drawPixmap(int(body.left()), int(body.top()), scaled)


def _build_document(card: Card, blocks: Mapping[int, Block], palette: Palette) -> QTextDocument:
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
    document.setDefaultFont(_font(UI_FONT, FONT_PX["body"]))
    # Code blocks and links must stay readable on the dark fill, where the markdown
    # importer's own light colours would otherwise paint dark-on-dark.
    document.setDefaultStyleSheet(_stylesheet(palette))
    document.setMarkdown("\n\n".join(parts))
    return document


def _draw_header_text(painter: QPainter, header: QRectF, card: Card, palette: Palette) -> None:
    glyph = KIND_GLYPH.get(card.kind, "•")
    painter.setPen(QPen(QColor(palette.text_secondary)))
    font = _font(UI_FONT, FONT_PX["control"], bold=True)
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
    painter.setPen(QPen(QColor(palette.text_primary)))
    painter.drawText(
        title_rect,
        int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
        elided,
    )
