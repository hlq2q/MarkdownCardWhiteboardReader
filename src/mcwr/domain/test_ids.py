"""Tests for identity and fingerprinting (decision D4)."""

from __future__ import annotations

from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from mcwr.domain.enums import CardKind
from mcwr.domain.ids import content_hash, document_path_hash, normalize_text, stable_key


def _key(**overrides: object) -> str:
    base: dict[str, object] = {
        "path_hash": "abc123",
        "heading_path": ("Intro", "Details"),
        "card_kind": CardKind.CODE,
        "ordinal_in_parent": 2,
        "occurrence": 1,
    }
    base.update(overrides)
    return stable_key(**base)  # type: ignore[arg-type]


def test_normalize_collapses_all_whitespace() -> None:
    assert normalize_text("  a \t b\r\n c \n\n") == "a b c"


def test_content_hash_ignores_whitespace_and_line_endings() -> None:
    assert content_hash("a  b\r\nc") == content_hash("a b\nc")


def test_content_hash_changes_with_text() -> None:
    assert content_hash("a b c") != content_hash("a b d")


def test_stable_key_is_independent_of_content() -> None:
    # The whole point of D4: content edits must not move a card's identity.
    first = _key()
    second = _key()
    assert first == second
    assert len(first) == 12


def test_stable_key_reacts_to_structure() -> None:
    assert _key() != _key(ordinal_in_parent=3)
    assert _key() != _key(occurrence=2)
    assert _key() != _key(card_kind=CardKind.TABLE)
    assert _key() != _key(heading_path=("Intro",))
    assert _key() != _key(path_hash="other")


def test_heading_path_segments_cannot_collide() -> None:
    # "\x1f" joins the segments, so ("a\x1fb",) must not equal ("a", "b").
    assert _key(heading_path=("a\x1fb",)) != _key(heading_path=("a", "b"))


def test_document_path_hash_is_case_insensitive(tmp_path: Path) -> None:
    upper = tmp_path / "Doc.md"
    lower = tmp_path / "doc.md"
    if not upper.exists():
        upper.write_text("x", encoding="utf-8")
        lower.write_text("x", encoding="utf-8")
    assert document_path_hash(upper) == document_path_hash(lower)


@given(st.text())
def test_normalize_is_idempotent(text: str) -> None:
    once = normalize_text(text)
    assert normalize_text(once) == once
