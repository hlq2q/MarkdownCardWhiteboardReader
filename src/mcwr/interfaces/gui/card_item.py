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
    QAbstractTextDocumentLayout,
    QBrush,
    QColor,
    QFont,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTextCursor,
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

from mcwr.application.features.build_toc.models import TocEntry
from mcwr.application.features.build_toc.service import toc_markdown
from mcwr.application.features.render_card.service import strip_fenced_block
from mcwr.domain.enums import BlockKind, CardKind
from mcwr.domain.models import Block, Card, CardLayout
from mcwr.infrastructure.pygments_highlighter import highlight_html
from mcwr.interfaces.gui.theme import (
    BORDER_WIDTH,
    CARD_RADIUS,
    CODE_FONT,
    CODE_FONT_FALLBACK,
    FONT_PX,
    HEADER_HEIGHT,
    LEVEL_BAR_WIDTH,
    LIGHT,
    MIN_LEGIBLE_ON_SCREEN_WIDTH,
    PADDING,
    SELECTED_WIDTH,
    SHADOW_RGBA,
    UI_FONT,
    UI_FONT_FALLBACK,
    Palette,
    card_fill,
    level_bar_colour,
    points,
    uses_shadow,
)

KIND_GLYPH: dict[CardKind, str] = {
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

    link_clicked = Signal(object, str)
    """A link inside the card body was clicked: (item, anchor without the leading ``#``)."""

    def __init__(
        self,
        card: Card,
        blocks: Mapping[int, Block],
        layout: CardLayout,
        image: QPixmap | None = None,
        palette: Palette = LIGHT,
        toc: tuple[TocEntry, ...] = (),
        depth: int = 0,
    ) -> None:
        super().__init__()
        self.card = card
        self.layout_state = layout
        self._blocks = blocks
        self._palette = palette
        self._toc = toc
        self._depth = max(depth, 0)
        self._cursor: QTextCursor | None = None
        self._scale = 1.0
        self._document = _build_document(card, blocks, palette, toc)
        self._image = image
        self._pending = False
        self._hovered = False
        self._dragging = False
        self._press_position: QPointF | None = None
        self._width = max(layout.width, 120.0)
        self._height = max(layout.height, self.header_height())
        # Lay the text out as soon as the geometry is known (not only in ``paint``): a click
        # can be hit-tested before the first paint, and ``anchor_at`` must answer then too.
        self._document.setTextWidth(self.body_rect().width())
        # Frozen until the window says otherwise: a card inside its parent keeps its position
        # relative to that parent and only moves when the parent does (T-043, D-050). Only free
        # cards and top-level cards are handed the movable flag.
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setCacheMode(QGraphicsObject.CacheMode.DeviceCoordinateCache)

    def set_movable(self, movable: bool) -> None:
        """Allow or refuse an independent drag (T-043, D-050).

        Qt moves an item on a left drag only while ``ItemIsMovable`` is set, so freezing the flag
        is what makes "a child inside its parent does not move on its own" true for the mouse too.
        The clamp in :meth:`itemChange` stays where it is: it keeps a programmatic placement
        inside the parent's rectangle as well.
        """
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsMovable, movable)

    # ------------------------------------------------------------------ geometry

    def boundingRect(self) -> QRectF:
        return QRectF(0.0, 0.0, self._width, self._height)

    @property
    def is_movable(self) -> bool:
        """Whether this card accepts an independent drag (T-043/D-050)."""
        return bool(self.flags() & QGraphicsObject.GraphicsItemFlag.ItemIsMovable)

    def is_in_header(self, scene_point: QPointF) -> bool:
        """Whether ``scene_point`` falls in this card's title bar (E-027)."""
        return 0.0 <= self.mapFromScene(scene_point).y() < self.header_height()

    def measured_body_height(self) -> float | None:
        """The height this card's body really needs, measured from its document (T-049).

        ``None`` for the kinds whose body is a rendered image: their document only holds a
        placeholder, so the layout keeps the text estimator in charge for them.
        """
        if self.card.kind in CardItem._IMAGE_KINDS:
            return None
        self._document.setTextWidth(self.body_rect().width())
        return self._document.size().height()

    def body_insets(self) -> tuple[float, float, float, float]:
        """Distance from the card's edge to the body element: left, right, top, bottom (T-053).

        Read-only view for tests. The four numbers have to agree for code, table and
        rendered-image cards, otherwise the element does not sit evenly inside its card.
        """
        layout = self._document.documentLayout()
        first = layout.blockBoundingRect(self._document.firstBlock())
        last = layout.blockBoundingRect(self._document.lastBlock())
        body = self.body_rect()
        return (
            body.left() + first.x(),
            self._width - (body.left() + first.x() + first.width()),
            body.top() - HEADER_HEIGHT + first.y(),
            self._height - (body.top() + last.bottom()),
        )

    # Bodies of these kinds are a rendered image, not the document: no height to measure (T-049).
    _IMAGE_KINDS = frozenset({CardKind.MATH_BLOCK, CardKind.MERMAID, CardKind.IMAGE})

    def begin_view_drag(self, point: QPointF) -> None:
        """Start a drag the *view* drives, with the same visual state as a normal one (E-027).

        Qt's own press delivery can hand a press on the title bar to the card behind it, so the
        view takes over for exactly those presses; this is the item-side half of that.
        """
        self._press_position = point
        self._dragging = True
        self.update()

    def end_view_drag(self) -> None:
        """Finish a view-driven drag: clear the drag state and report the position (E-027)."""
        self._dragging = False
        self.update()
        moved = self._press_position is None or self._press_position != self.scenePos()
        self._press_position = None
        if moved:
            position = self.scenePos()
            self.moved.emit(self, position.x(), position.y())

    def set_card_geometry(self, width: float, height: float) -> None:
        if (width, height) == (self._width, self._height):
            return
        self.prepareGeometryChange()
        self._width = max(width, 120.0)
        self._height = max(height, self.header_height())
        self._document.setTextWidth(self.body_rect().width())

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

    # ----------------------------------------------------------------- text selection (T-063)

    def has_selection(self) -> bool:
        """Whether this card currently shows a text selection."""
        return self._cursor is not None and self._cursor.hasSelection()

    def selected_text(self) -> str:
        """The selected text, with Qt's paragraph separators turned into newlines."""
        if self._cursor is None:
            return ""
        return self._cursor.selectedText().replace("\u2029", "\n")

    def clear_selection(self) -> None:
        """Drop the selection (a press on another card does this); repaints if there was one."""
        if self._cursor is None:
            return
        self._cursor = None
        self.update()

    def start_selection(self, scene_point: QPointF) -> bool:
        """Begin a selection where ``scene_point`` falls in the body; False for an image body."""
        position = self._text_position(scene_point)
        if position is None:
            return False
        self._cursor = QTextCursor(self._document)
        self._cursor.setPosition(position)
        self.update()
        return True

    def extend_selection(self, scene_point: QPointF) -> None:
        """Grow the selection towards ``scene_point``; the anchor stays where the drag began."""
        if self._cursor is None:
            return
        position = self._text_position(scene_point)
        if position is None:
            return
        self._cursor.setPosition(position, QTextCursor.MoveMode.KeepAnchor)
        self.update()

    def has_text_at(self, scene_point: QPointF) -> bool:
        """Whether a scene point sits on this card's text (the I-beam area, T-065)."""
        return self._text_position(scene_point) is not None

    def anchor_at_scene(self, scene_point: QPointF) -> str:
        """The href of the link under a *scene* point, or an empty string (FR-2.4, T-063)."""
        body = self.body_rect()
        local = self.mapFromScene(scene_point)
        if not body.contains(local):
            return ""
        return self._document.documentLayout().anchorAt(local - body.topLeft())

    def _text_position(self, scene_point: QPointF) -> int | None:
        """The document position under a scene point, clamped into the body; None for an image."""
        if self.has_image:
            return None  # an image body is not text
        body = self.body_rect()
        local = self.mapFromScene(scene_point)
        inside = (
            QPointF(
                min(max(local.x(), body.left()), body.right()),
                min(max(local.y(), body.top()), body.bottom()),
            )
            - body.topLeft()
        )
        return self._document.documentLayout().hitTest(inside, Qt.HitTestAccuracy.FuzzyHit)

    def _draw_body_text(self, painter: QPainter) -> None:
        """Draw the body text, highlighting the selection when there is one (T-063).

        Without a selection this stays the plain ``drawContents`` path, so the everyday look is
        untouched; a selection needs an explicit paint context, the only way to hand the cursor to
        the layout.
        """
        rect = QRectF(0, 0, self.body_rect().width(), 1e6)
        if not self.has_selection():
            self._document.drawContents(painter, rect)
            return
        assert self._cursor is not None
        context = QAbstractTextDocumentLayout.PaintContext()
        context.clip = rect
        context.palette = QGuiApplication.palette()  # the same palette drawContents() would use
        selection = QAbstractTextDocumentLayout.Selection()
        selection.cursor = self._cursor
        highlight = QColor(self._palette.selected)
        highlight.setAlpha(90)
        selection.format.setBackground(QBrush(highlight))
        context.selections = [selection]
        self._document.documentLayout().draw(painter, context)

    def header_height(self) -> float:
        """The title bar's height: the base height times this card's effective scale (T-057)."""
        return HEADER_HEIGHT * self._scale

    @property
    def effective_scale(self) -> float:
        """The scale this card is drawn with; the placer computed it (T-064/D-060)."""
        return self._scale

    def set_scale(self, scale: float) -> None:
        """Use ``scale`` for this card's fonts and title bar, re-rendering when it changes (T-057).

        The geometry comes from the layout, which scales the box the same way; this only makes the
        painted content match, so a scaled card's text is drawn at the right size in its box.
        """
        if scale == self._scale:
            return
        self._scale = max(scale, 0.05)
        self._document = _build_document(
            self.card, self._blocks, self._palette, self._toc, scale=self._scale
        )
        self._document.setTextWidth(self.body_rect().width())
        self.update()

    def body_rect(self) -> QRectF:
        """The area the body is drawn in, inset equally on all four sides (T-053).

        It used to start right under the header bar: measured against a code card, the element's
        distance to the card edge was 10 px left and right (PADDING + the document's own margin) but
        4 px above and 16 px below. Inset by PADDING at the top as well, and the document's 4 px
        margin then lands on the same 10 px on every side -- while the height still equals the
        measured body exactly (header + body + 2 * PADDING is what the layout reserves).
        """
        header = self.header_height()
        return QRectF(
            PADDING,
            header + PADDING,
            max(self._width - 2 * PADDING, 1.0),
            max(self._height - header - 2 * PADDING, 1.0),
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
        self._document = _build_document(self.card, self._blocks, palette, self._toc)
        self.update()

    def anchor_at(self, point: QPointF) -> str:
        """The anchor of the link drawn under an item-local ``point`` (``""`` if none).

        The body is painted with the document translated to ``body_rect().topLeft()``, so a
        click is mapped back the same way before asking the layout which character it hit;
        ``QTextCharFormat.isAnchor()`` then says whether that character is a link.
        """
        local = point - self.body_rect().topLeft()
        position = self._document.documentLayout().hitTest(local, Qt.HitTestAccuracy.ExactHit)
        if position < 0:
            return ""
        cursor = QTextCursor(self._document)
        cursor.setPosition(position)
        cursor.movePosition(
            QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor
        )
        char_format = cursor.charFormat()
        return char_format.anchorHref().lstrip("#") if char_format.isAnchor() else ""

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
        reduced = self.uses_reduced_detail(painter.transform().m11())
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
        _draw_depth_bar(painter, frame, palette, self._depth, clipped=not reduced)

        header = QRectF(frame.left(), frame.top(), frame.width(), self.header_height())
        painter.setPen(QPen(QColor(palette.border), BORDER_WIDTH))
        painter.drawLine(
            QPointF(frame.left(), header.bottom()), QPointF(frame.right(), header.bottom())
        )
        _draw_header_text(painter, header, self.card, palette, self._scale)

        if not reduced:
            # T-033: below the thumbnail threshold the body is not laid out, not resampled and
            # not drawn. That is where the per-card time went (docs/performance.md §4): the
            # visible shape, border, stripe and header bar still say which card this is.
            painter.save()
            painter.setClipRect(self.body_rect())
            if self.has_image and self._image is not None:
                _draw_body_image(painter, self.body_rect(), self._image)
            else:
                painter.translate(self.body_rect().topLeft())
                painter.setPen(QPen(QColor(palette.text_primary)))
                self._document.setTextWidth(self.body_rect().width())
                self._draw_body_text(painter)
            painter.restore()

        # Selection is a thicker border *and* another colour, never colour alone (§6).
        edge = QColor(palette.selected) if selected else QColor(palette.card_edge)
        width = SELECTED_WIDTH if selected else BORDER_WIDTH
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(edge, width))
        painter.drawRoundedRect(frame, CARD_RADIUS, CARD_RADIUS)

        if self._pending and not self.has_image:
            _draw_pending_badge(painter, header, palette)

    def uses_reduced_detail(self, scale: float) -> bool:
        """Whether this card is small enough on screen to be painted in its reduced form.

        ``scale`` is the painter's current scale, i.e. the zoom the user is at, so this is the
        same measure T-031 uses for its render floor (``MIN_LEGIBLE_ON_SCREEN_WIDTH``). Below
        that width the card is a thumbnail: its body text cannot be read, and resampling a body
        image is work nobody can see.
        """
        return self._width * scale < MIN_LEGIBLE_ON_SCREEN_WIDTH

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
            self._press_position = self.scenePos()
            anchor = self.anchor_at(event.pos())
            if anchor:
                # A link click navigates; it must not start a drag (FR-2.4).
                self.link_clicked.emit(self, anchor)
                event.accept()
                return
            if self.flags() & QGraphicsObject.GraphicsItemFlag.ItemIsMovable:
                self._dragging = True
                self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if self._dragging:
            self._dragging = False
            self.update()
        # Only a real move is a move: a plain click (a link, a selection) used to emit
        # ``moved`` as well, which recorded a no-op drag and overwrote the status message.
        moved = self._press_position is None or self._press_position != self.scenePos()
        self._press_position = None
        if moved:
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


def _draw_depth_bar(
    painter: QPainter, frame: QRectF, palette: Palette, depth: int, *, clipped: bool = True
) -> None:
    """A 3 px stripe on the left edge carrying the nesting depth (visual spec §6.1).

    Clipped to the card's rounded outline so the stripe follows the corner radius; the card
    border is painted afterwards and therefore stays visible on top of it. ``clipped=False``
    is the thumbnail path (T-033): no ``QPainterPath`` and no clip state, which is the whole
    point of not doing the work twice.
    """
    if clipped:
        outline = QPainterPath()
        outline.addRoundedRect(frame, CARD_RADIUS, CARD_RADIUS)
        painter.save()
        painter.setClipPath(outline)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor(level_bar_colour(palette, depth))))
    painter.drawRect(QRectF(frame.left(), frame.top(), LEVEL_BAR_WIDTH, frame.height()))
    if clipped:
        painter.restore()


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


def _build_document(
    card: Card,
    blocks: Mapping[int, Block],
    palette: Palette,
    toc: tuple[TocEntry, ...] = (),
    *,
    scale: float = 1.0,
) -> QTextDocument:
    """Render this card's own blocks (never its children's) as Markdown text.

    Two exceptions: a TOC card draws the generated heading links (FR-2.4), and a CODE card
    draws lexically highlighted code (T-029). Everything else keeps the Markdown path.
    """
    document = QTextDocument()
    document.setDefaultFont(_font(UI_FONT, FONT_PX["body"] * scale))
    # Code blocks and links must stay readable on the dark fill, where the markdown
    # importer's own light colours would otherwise paint dark-on-dark.
    document.setDefaultStyleSheet(_stylesheet(palette))
    # One source of padding only (T-054): Qt's default 4 px document margin would otherwise add
    # to PADDING and make the element sit 10 px from the edges instead of the intended 6.
    document.setDocumentMargin(0.0)

    code = _own_code_block(card, blocks)
    if code is not None:
        document.setHtml(_code_html(code, palette))
        return document

    parts: list[str] = []
    if card.kind is CardKind.TOC:
        parts.append(toc_markdown(toc))
    else:
        for index in card.own_block_indexes:
            block = blocks.get(index)
            if block is None:
                continue
            if card.kind is CardKind.HEADING and block.index == card.block_index:
                continue  # a heading's text already lives in the header bar
            text = block.raw_text.strip()
            if text:
                parts.append(text)
    document.setMarkdown("\n\n".join(parts))
    return document


def _own_code_block(card: Card, blocks: Mapping[int, Block]) -> Block | None:
    """The code block a CODE card draws, or ``None`` for every other card.

    Highlighting takes over the body only when the card owns exactly one block that is code;
    a hypothetical mixed code card keeps the Markdown path, so prose, tables and formulas are
    never touched by this feature.
    """
    if card.kind is not CardKind.CODE or len(card.own_block_indexes) != 1:
        return None
    block = blocks.get(card.own_block_indexes[0])
    if block is None or block.kind is not BlockKind.CODE:
        return None
    return block


def _code_html(block: Block, palette: Palette) -> str:
    """A ``<pre>`` block of highlighted code on the palette's code background.

    The fence is stripped first: the IR keeps it, but it is Markdown syntax, not code (the
    old Markdown path hid it because the importer consumed it — ERRORS.md E-022).

    No wrapping is requested: the card draws code exactly as it did before this feature, only
    with coloured tokens (superfluous layout changes are not part of T-029).
    """
    body = highlight_html(
        strip_fenced_block(block.raw_text),
        block.lang,
        style=palette.pygments_style,
        background=palette.code_bg,
        fallback=palette.text_secondary,
    )
    return (
        f'<pre style="background-color:{palette.code_bg}; '
        f'color:{palette.text_primary}; margin:0;">{body}</pre>'
    )


def _draw_header_text(
    painter: QPainter, header: QRectF, card: Card, palette: Palette, scale: float = 1.0
) -> None:
    glyph = KIND_GLYPH.get(card.kind, "•")
    painter.setPen(QPen(QColor(palette.text_secondary)))
    font = _font(UI_FONT, FONT_PX["control"] * scale, bold=True)
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
