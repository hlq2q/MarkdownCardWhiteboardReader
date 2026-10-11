"""markdown-it-py adapter: token stream -> block sequence (IR).

Classification rules were verified by `spikes/spike_md_blocks.py`; see `spikes/NOTES.md`.
Nothing here writes to the source file, and no token shape may raise: unknown tokens
degrade to an ``unknown`` block so the raw text is never lost (FR-1.5).
"""

from __future__ import annotations

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.tasklists import tasklists_plugin

from mcwr.domain.enums import BlockKind
from mcwr.domain.ids import normalize_text
from mcwr.domain.models import Block, InlineSpan, SourceSpan

_TOC_MARKERS = frozenset({"[TOC]", "[[TOC]]"})
_LIST_OPEN_TYPES = frozenset({"bullet_list_open", "ordered_list_open"})


def build_parser() -> MarkdownIt:
    """Configured parser: CommonMark + tables + dollar math + task lists + raw HTML."""
    md = MarkdownIt("commonmark", {"html": True}).enable("table")
    md.use(dollarmath_plugin, allow_space=True)
    md.use(tasklists_plugin)
    return md


class MarkdownItBlockParser:
    """Implements the ``BlockParser`` port using markdown-it-py."""

    def __init__(self, md: MarkdownIt | None = None) -> None:
        self._md = md or build_parser()

    def parse(self, text: str) -> tuple[Block, ...]:
        return _BlockCollector(text).collect(self._md.parse(text))


class _BlockCollector:
    """Walks top-level tokens and emits blocks with stable document indexes."""

    def __init__(self, text: str) -> None:
        self._lines = text.splitlines()
        self._blocks: list[Block] = []

    # ------------------------------------------------------------------ emitting

    def collect(self, tokens: list[Token]) -> tuple[Block, ...]:
        index = 0
        while index < len(tokens):
            token = tokens[index]
            kind = token.type
            if kind == "heading_open":
                self._emit_heading(token, _next_inline(tokens, index))
                index += 3
            elif kind == "paragraph_open":
                self._emit_paragraph(token, _next_inline(tokens, index))
                index += 3
            elif kind == "blockquote_open":
                close = _matching_close(tokens, index)
                self._emit_container(BlockKind.BLOCKQUOTE, token, tokens[index:close])
                index = close + 1
            elif kind in _LIST_OPEN_TYPES:
                close = _matching_close(tokens, index)
                self._emit_list(token, tokens[index:close])
                index = close + 1
            elif kind == "table_open":
                close = _matching_close(tokens, index)
                self._emit_container(BlockKind.TABLE, token, tokens[index:close])
                index = close + 1
            elif kind == "fence":
                self._emit_fence(token)
                index += 1
            elif kind == "math_block":
                self._emit_math(token)
                index += 1
            elif kind == "html_block":
                self._emit_html(token)
                index += 1
            elif kind == "hr":
                self._emit(BlockKind.THEMATIC_BREAK, token, "")
                index += 1
            elif kind.endswith("_close") or kind == "inline":
                index += 1
            else:
                self._emit(BlockKind.UNKNOWN, token, token.content)
                index += 1
        return tuple(self._blocks)

    def _emit(
        self,
        kind: BlockKind,
        token: Token | None,
        text: str,
        *,
        level: int | None = None,
        lang: str | None = None,
        inline: tuple[InlineSpan, ...] = (),
        attrs: dict[str, str] | None = None,
    ) -> Block:
        block = Block(
            index=len(self._blocks),
            kind=kind,
            raw_text=self._raw(token),
            text_normalized=normalize_text(text),
            level=level,
            lang=lang,
            inline=inline,
            span=_span(token),
            attrs=dict(attrs or {}),
        )
        self._blocks.append(block)
        return block

    def _raw(self, token: Token | None) -> str:
        if token is None or not token.map:
            return ""
        start, end = token.map
        return "\n".join(self._lines[start:end])

    # ---------------------------------------------------------------- dispatchers

    def _emit_heading(self, token: Token, inline: Token | None) -> None:
        level = int(token.tag[1:]) if token.tag[:1] == "h" and token.tag[1:].isdigit() else 1
        text = inline.content if inline is not None else ""
        self._emit(
            BlockKind.HEADING,
            token,
            text,
            level=level,
            inline=inline_spans(inline),
        )

    def _emit_paragraph(self, token: Token, inline: Token | None) -> None:
        children = list(inline.children or []) if inline is not None else []
        text = inline.content if inline is not None else ""
        images = [child for child in children if child.type == "image"]
        plain = "".join(child.content for child in children if child.type == "text").strip()

        if plain.upper() in _TOC_MARKERS and not images:
            self._emit(BlockKind.TOC, token, plain)
            return
        if images and not plain and _only_media(children):
            self._emit_images(token, images)
            return
        self._emit(BlockKind.PARAGRAPH, token, text, inline=inline_spans(inline))

    def _emit_images(self, token: Token, images: list[Token]) -> None:
        for child in images:
            attrs = {key: str(value) for key, value in (child.attrs or {}).items()}
            self._emit(
                BlockKind.IMAGE,
                token,
                child.content,
                inline=(InlineSpan("image", child.content, attrs.get("src")),),
                attrs=attrs,
            )

    def _emit_container(self, kind: BlockKind, token: Token, window: list[Token]) -> None:
        text = "\n".join(child.content for child in window if child.type == "inline")
        self._emit(kind, token, text)

    def _emit_list(self, token: Token, window: list[Token]) -> None:
        attrs = {key: str(value) for key, value in (token.attrs or {}).items()}
        is_task_list = attrs.get("class") == "contains-task-list"
        # The checkbox lives inside the inline token's children, not in the window.
        checked = sum(
            1
            for child in window
            for grand in (child.children or [])
            if grand.type == "html_inline" and "checked" in grand.content
        )
        total = sum(1 for child in window if child.type == "list_item_open")
        text = "\n".join(child.content for child in window if child.type == "inline")
        if is_task_list:
            attrs |= {"checked": str(checked), "total": str(max(total, checked))}
            self._emit(BlockKind.TASK_LIST, token, text, attrs=attrs)
        else:
            self._emit(BlockKind.LIST, token, text)

    def _emit_fence(self, token: Token) -> None:
        info = (token.info or "").strip()
        lang = info.split()[0] if info else ""
        kind = BlockKind.MERMAID if lang.lower() == "mermaid" else BlockKind.CODE
        self._emit(kind, token, token.content.strip("\n"), lang=lang or None)

    def _emit_math(self, token: Token) -> None:
        self._emit(BlockKind.MATH_BLOCK, token, token.content.strip())

    def _emit_html(self, token: Token) -> None:
        self._emit(BlockKind.HTML, token, token.content)


def _next_inline(tokens: list[Token], index: int) -> Token | None:
    following = tokens[index + 1] if index + 1 < len(tokens) else None
    return following if following is not None and following.type == "inline" else None


def _matching_close(tokens: list[Token], open_index: int) -> int:
    """Index of the token that closes the container opened at ``open_index``."""
    depth = 0
    for index in range(open_index, len(tokens)):
        depth += tokens[index].nesting
        if depth == 0:
            return index
    return len(tokens) - 1


def _span(token: Token | None) -> SourceSpan | None:
    if token is None or not token.map:
        return None
    start, end = token.map
    if end <= start:
        return None
    return SourceSpan(start_line=start + 1, end_line=end)


def _only_media(children: list[Token]) -> bool:
    """True when a paragraph holds nothing but images and breaks."""
    allowed = {"image", "softbreak", "hardbreak", "html_inline"}
    return all(child.type in allowed for child in children)


def inline_spans(inline: Token | None) -> tuple[InlineSpan, ...]:
    """Flatten inline children into spans kept for search and future rendering."""
    if inline is None:
        return ()
    spans: list[InlineSpan] = []
    href: str | None = None
    for child in inline.children or []:
        kind = child.type
        if kind == "text":
            spans.append(InlineSpan("link" if href else "text", child.content, href))
        elif kind == "code_inline":
            spans.append(InlineSpan("code", child.content))
        elif kind == "math_inline":
            spans.append(InlineSpan("math", child.content))
        elif kind == "image":
            raw_src = (child.attrs or {}).get("src")
            target = None if raw_src is None else str(raw_src)
            spans.append(InlineSpan("image", child.content, target))
        elif kind in {"softbreak", "hardbreak"}:
            spans.append(InlineSpan("break", "\n"))
        elif kind == "html_inline":
            spans.append(InlineSpan("html", child.content))
        elif kind == "link_open":
            href = str((child.attrs or {}).get("href", ""))
        elif kind == "link_close":
            href = None
    return tuple(spans)
