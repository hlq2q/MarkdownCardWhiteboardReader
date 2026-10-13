"""Tests for the render_card use case: hand-written fakes, no Qt, no filesystem writes."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcwr.application.features.render_card.ports import WebCardRenderer
from mcwr.application.features.render_card.service import (
    WEB_RENDER_KINDS,
    card_image,
    needs_web_render,
    strip_fenced_block,
    web_source,
)
from mcwr.domain.enums import BlockKind, CardKind
from mcwr.domain.models import Block, Card


class FakeWebRenderer:
    """Records every call; optionally pretends rendering is impossible."""

    def __init__(self, result: Path | None = None) -> None:
        self.result = result
        self.calls: list[tuple[CardKind, str, float]] = []
        self.themes: list[str] = []

    def render(
        self, *, kind: CardKind, source: str, scale: float, theme: str = "light"
    ) -> Path | None:
        self.calls.append((kind, source, scale))
        self.themes.append(theme)
        return self.result


def _card(kind: CardKind, *, block_index: int | None = 0, own: tuple[int, ...] = (0,)) -> Card:
    return Card(
        card_id=f"card-{kind.value}",
        kind=kind,
        parent_id=None,
        child_ids=(),
        own_block_indexes=own,
        heading_path=("Intro",),
        ordinal_in_parent=0,
        occurrence=0,
        content_hash="deadbeef",
        title=kind.value,
        block_index=block_index,
    )


def _block(index: int, kind: BlockKind, raw_text: str, *, lang: str | None = None) -> Block:
    return Block(
        index=index,
        kind=kind,
        raw_text=raw_text,
        text_normalized=raw_text,
        lang=lang,
    )


def _math_block(index: int = 0, body: str = r"\int_0^1 x^2\,dx") -> Block:
    return _block(index, BlockKind.MATH_BLOCK, f"$$\n{body}\n$$")


def _mermaid_block(index: int = 0, body: str = "graph TD\n  A --> B") -> Block:
    return _block(index, BlockKind.MERMAID, f"```mermaid\n{body}\n```", lang="mermaid")


# ------------------------------------------------------------------ which kinds


_WEB_RENDER_EXPECTED: list[CardKind] = [CardKind.MATH_BLOCK, CardKind.MERMAID]


def test_only_math_and_mermaid_need_a_web_render() -> None:
    assert sorted(WEB_RENDER_KINDS) == _WEB_RENDER_EXPECTED


_TEXT_ONLY_KINDS: tuple[CardKind, ...] = (
    CardKind.CODE,
    CardKind.TABLE,
    CardKind.HEADING,
    CardKind.FALLBACK_TEXT,
    CardKind.IMAGE,
    CardKind.TASK_LIST,
    CardKind.TOC,
)


@pytest.mark.parametrize("kind", sorted(set(CardKind) - WEB_RENDER_KINDS))
def test_text_cards_need_no_web_render(kind: CardKind) -> None:
    assert needs_web_render(_card(kind)) is False


@pytest.mark.parametrize("kind", sorted(WEB_RENDER_KINDS))
def test_math_and_mermaid_need_a_web_render(kind: CardKind) -> None:
    assert needs_web_render(_card(kind)) is True


def test_the_text_only_kinds_are_the_ones_without_a_web_renderer() -> None:
    """The set is exhaustive, so a new CardKind cannot silently lose its rendering."""
    assert set(_TEXT_ONLY_KINDS) == set(CardKind) - WEB_RENDER_KINDS


# ----------------------------------------------------------------- source extraction


def test_math_source_is_the_latex_body_without_the_dollar_fences() -> None:
    blocks = {0: _math_block(0, r"e^{i\pi}+1=0")}
    assert web_source(_card(CardKind.MATH_BLOCK), blocks, 0) == r"e^{i\pi}+1=0"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$$x^2$$", "x^2"),  # inline fences on one line
        ("$$\n  x^2\n$$", "x^2"),  # display fences on their own lines
        (r"\[x^2\]", "x^2"),  # LaTeX display delimiters
        (r"\(x^2\)", "x^2"),  # LaTeX inline delimiters
        ("$x^2$", "x^2"),  # bare single dollars
        ("x^2", "x^2"),  # already a body
        ("$5 and $6", "$5 and $6"),  # not math: no matching closer
    ],
)
def test_math_fences_are_stripped(raw: str, expected: str) -> None:
    blocks = {0: _block(0, BlockKind.MATH_BLOCK, raw)}
    assert web_source(_card(CardKind.MATH_BLOCK), blocks, 0) == expected


def test_math_body_keeps_internal_line_breaks() -> None:
    body = "\\begin{aligned}\na &= b \\\\\nc &= d\n\\end{aligned}"
    raw = "$$\n" + body + "\n$$"
    assert body.endswith("\\end{aligned}")  # the fixture really holds LaTeX rows
    blocks = {0: _block(0, BlockKind.MATH_BLOCK, raw)}
    assert web_source(_card(CardKind.MATH_BLOCK), blocks, 0) == body


def test_mermaid_source_is_the_fence_body() -> None:
    blocks = {0: _mermaid_block(0, "graph TD\n  A --> B")}
    assert web_source(_card(CardKind.MERMAID), blocks, 0) == "graph TD\n  A --> B"


def test_mermaid_source_drops_the_info_string_but_keeps_indentation() -> None:
    body = "sequenceDiagram\n    A->>B: hi\n    B-->>A: ok"
    blocks = {0: _mermaid_block(0, body)}
    assert web_source(_card(CardKind.MERMAID), blocks, 0) == body


def test_unfenced_mermaid_source_is_passed_through() -> None:
    blocks = {0: _block(0, BlockKind.MERMAID, "graph LR\n  X --> Y")}
    assert web_source(_card(CardKind.MERMAID), blocks, 0) == "graph LR\n  X --> Y"


def test_non_web_kind_has_no_source() -> None:
    blocks = {0: _block(0, BlockKind.CODE, "```python\nprint(1)\n```", lang="python")}
    assert web_source(_card(CardKind.CODE), blocks, 0) is None


def test_missing_block_has_no_source() -> None:
    assert web_source(_card(CardKind.MATH_BLOCK), {}, 0) is None


def test_empty_math_body_has_no_source() -> None:
    blocks = {0: _block(0, BlockKind.MATH_BLOCK, "$$\n\n$$")}
    assert web_source(_card(CardKind.MATH_BLOCK), blocks, 0) is None


def test_blank_primary_block_falls_back_to_the_first_own_block_with_content() -> None:
    blocks = {
        0: _block(0, BlockKind.PARAGRAPH, "   "),
        1: _math_block(1, "a+b"),
    }
    card = _card(CardKind.MATH_BLOCK, block_index=0, own=(0, 1))
    assert web_source(card, blocks, 0) == "a+b"


# ----------------------------------------------------------------------- card_image


def test_card_image_passes_kind_source_and_scale_to_the_renderer() -> None:
    blocks = {0: _math_block(0, "a+b")}
    renderer = FakeWebRenderer(Path("C:/cache/web-math-ab.png"))
    result = card_image(_card(CardKind.MATH_BLOCK), blocks, renderer=renderer, scale=1.5)
    assert result == Path("C:/cache/web-math-ab.png")
    assert renderer.calls == [(CardKind.MATH_BLOCK, "a+b", 1.5)]


def test_card_image_is_none_when_the_renderer_fails_so_the_view_keeps_its_text() -> None:
    blocks = {0: _mermaid_block(0)}
    renderer = FakeWebRenderer(None)
    assert card_image(_card(CardKind.MERMAID), blocks, renderer=renderer, scale=2.0) is None
    assert len(renderer.calls) == 1  # it did try, and the caller falls back


def test_card_image_never_calls_the_renderer_for_text_cards() -> None:
    blocks = {0: _block(0, BlockKind.TABLE, "| a | b |\n| - | - |")}
    renderer = FakeWebRenderer(Path("unused.png"))
    assert card_image(_card(CardKind.TABLE), blocks, renderer=renderer, scale=1.0) is None
    assert renderer.calls == []


def test_card_image_does_not_call_the_renderer_without_a_source() -> None:
    renderer = FakeWebRenderer(Path("unused.png"))
    assert card_image(_card(CardKind.MATH_BLOCK), {}, renderer=renderer, scale=1.0) is None
    assert renderer.calls == []


def test_card_image_accepts_a_card_without_a_primary_block_index() -> None:
    blocks = {0: _math_block(0, "a+b")}
    renderer = FakeWebRenderer(Path("hit.png"))
    card = _card(CardKind.MATH_BLOCK, block_index=None, own=(0,))
    assert card_image(card, blocks, renderer=renderer, scale=1.0) == Path("hit.png")
    assert renderer.calls == [(CardKind.MATH_BLOCK, "a+b", 1.0)]


def test_the_fake_satisfies_the_port() -> None:
    """The port is structural: a plain object with the right signature is a renderer."""
    renderer: WebCardRenderer = FakeWebRenderer(None)
    assert renderer.render(kind=CardKind.MATH_BLOCK, source="x", scale=1.0) is None


# ------------------------------------------------------------- fence stripping (T-029)


def test_a_code_fence_is_stripped_with_its_info_string() -> None:
    assert strip_fenced_block("```python\nx = 1\n```") == "x = 1"


def test_a_tilde_fence_is_stripped_too() -> None:
    assert strip_fenced_block("~~~mermaid\ngraph TD; A-->B;\n~~~") == "graph TD; A-->B;"


def test_a_body_without_a_fence_is_only_trimmed() -> None:
    assert strip_fenced_block("  plain body  \n") == "plain body"


def test_a_lonely_fence_is_not_treated_as_a_pair() -> None:
    assert strip_fenced_block("```") == "```"


def test_the_mermaid_helper_keeps_working_through_the_shared_one() -> None:
    """The Mermaid path predates this helper; it must keep its behaviour (T-029 refactor)."""
    from mcwr.application.features.render_card.service import _strip_mermaid_fence

    assert _strip_mermaid_fence("```mermaid\ngraph TD;\n```") == "graph TD;"


def test_card_image_renders_the_bare_body_not_the_fence() -> None:
    """The renderer must never see the fence: it would draw it as content (E-022)."""
    blocks = {0: _block(0, BlockKind.MATH_BLOCK, "$$\na+b\n$$")}
    renderer = FakeWebRenderer(Path("x.png"))
    card_image(_card(CardKind.MATH_BLOCK), blocks, renderer=renderer, scale=1.0)
    assert renderer.calls == [(CardKind.MATH_BLOCK, "a+b", 1.0)]

    code_blocks = {0: _block(0, BlockKind.CODE, "```python\nprint(1)\n```", lang="python")}
    stripped = strip_fenced_block(code_blocks[0].raw_text)
    assert stripped == "print(1)"
