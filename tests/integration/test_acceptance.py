"""The ten acceptance criteria of docs/requirements-spec.md §1.5, verified end to end."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PySide6.QtCore import QPointF

from mcwr.domain.enums import CardKind
from mcwr.interfaces.gui.main_window import MainWindow

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "spikes" / "samples" / "sample.md"


def open_sample(window: MainWindow, tmp_path: Path | None = None) -> Path:
    if tmp_path is None:
        assert window.open_path(SAMPLE) is True
        return SAMPLE
    copy = tmp_path / "doc.md"
    shutil.copyfile(SAMPLE, copy)
    assert window.open_path(copy) is True
    return copy


def card_id_of(window: MainWindow, title: str) -> str:
    document = window.session.document
    assert document is not None
    matches = [card.card_id for card in document.tree.cards.values() if card.title == title]
    assert len(matches) == 1, f"expected one card titled {title!r}"
    return matches[0]


@pytest.fixture
def window() -> MainWindow:
    return MainWindow(persist=False)


def test_acceptance_1_cards_are_laid_out_along_the_document_order(window: MainWindow) -> None:
    open_sample(window)
    document = window.session.document
    assert document is not None
    ys = [window.session.layouts[card_id].y for card_id in document.tree.ordered_ids()]
    assert ys == sorted(ys)
    assert len(set(ys)) > 1


def test_acceptance_2_dividers_and_headings_nest_correctly(window: MainWindow) -> None:
    open_sample(window)
    document = window.session.document
    assert document is not None
    tree = document.tree
    roots = [tree.cards[root] for root in tree.root_ids]
    assert all(card.kind is CardKind.HEADING for card in roots), "the top-level headings are roots"
    assert len(roots) == 1, "the sample has one H1, and the divider adds no card (T-055)"

    task_list = card_id_of(window, "tasks")
    parent = tree.cards[tree.cards[task_list].parent_id or ""]
    assert parent.title == "Task list"
    assert tree.cards[task_list].heading_path == (
        "Spike sample: every block kind the card builder must classify.",
        "Task list",
    )
    level_three = card_id_of(window, "Level jump from H3 (parent is the H2 above)")
    assert tree.cards[level_three].level == 3
    toc_heading = next(
        card
        for card in tree.cards.values()
        if card.kind is CardKind.HEADING and card.title == "TOC"
    )
    assert tree.cards[level_three].parent_id == toc_heading.card_id, "an H3 attaches to the H2"


def test_acceptance_3_prose_lists_and_quotes_are_not_cards(window: MainWindow) -> None:
    open_sample(window)
    document = window.session.document
    assert document is not None
    kinds = {card.kind for card in document.tree.cards.values()}
    assert CardKind.FALLBACK_TEXT not in kinds
    card_kinds = {card.block_index for card in document.tree.cards.values() if card.block_index}
    content_owner = [
        card
        for card in document.tree.cards.values()
        if any(index not in card_kinds for index in card.own_block_indexes)
    ]
    assert content_owner, "paragraphs/quotes/lists must live inside some card"
    owners = {index for card in content_owner for index in card.own_block_indexes}
    prose_indexes = {
        block.index
        for block in document.blocks
        if block.kind.value in {"paragraph", "blockquote", "list"}
    }
    assert prose_indexes <= owners, "no prose block may be dropped"


def test_acceptance_4_a_child_cannot_be_dragged_out_before_detaching(window: MainWindow) -> None:
    open_sample(window)
    code = card_id_of(window, "python")
    item = window.card_items[code]
    parent_item = item.parentItem()
    assert parent_item is not None

    item.setPos(QPointF(-5000.0, -5000.0))

    assert item.pos().x() >= 0.0
    assert item.pos().y() >= 0.0
    assert item.parentItem() is parent_item, "the card must stay inside its parent"

    window.session.detach(code)
    item = window.card_items[code]
    item.setPos(QPointF(-5000.0, -5000.0))
    assert item.pos().x() == -5000.0, "a free card moves without constraint"


def test_acceptance_5_restore_all_returns_the_initial_arrangement(window: MainWindow) -> None:
    open_sample(window)
    first = card_id_of(window, "python")
    second = card_id_of(window, "mermaid")
    window.session.detach(first)
    window.session.detach(second)
    window.card_items[first].setPos(QPointF(3000.0, 3000.0))

    window.session.restore_all()

    document = window.session.document
    assert document is not None
    assert all(not layout.detached for layout in window.session.layouts.values())
    ys = [window.session.layouts[card_id].y for card_id in document.tree.ordered_ids()]
    assert ys == sorted(ys)
    assert window.card_items[first].parentItem() is not None


def test_acceptance_6_refresh_keeps_layout_unless_the_structure_changes(
    window: MainWindow, tmp_path: Path
) -> None:
    document_path = open_sample(window, tmp_path)
    code = card_id_of(window, "python")
    # A card inside its parent cannot be moved (T-043/D-050): an arrangement the app can really
    # produce needs a movable card, so detach it before placing it.
    window.session.detach(code)
    window.session.layouts[code].move_to(700.0, 900.0)

    with document_path.open("a", encoding="utf-8") as handle:
        handle.write("\nAn added paragraph of prose.\n")
    assert window.session.refresh() is True
    assert window.session.layouts[code].x == 700.0, "prose edits are not a major change"

    with document_path.open("a", encoding="utf-8") as handle:
        handle.write("\n---\n\n## Whole new section\n\ntext\n")
    assert window.session.refresh() is True
    document = window.session.document
    assert document is not None
    titles = [document.tree.cards[root].title for root in document.tree.root_ids]
    assert len(titles) == 1, "a divider adds no card, and the added ## nests (T-055)"


def test_acceptance_6b_changing_a_heading_level_is_a_major_change(
    window: MainWindow, tmp_path: Path
) -> None:
    """D11, checked end to end and independently of the slice's own unit tests."""
    document_path = tmp_path / "levels.md"
    document_path.write_text(
        "# Title\n\nintro\n\n## Section\n\n```python\nprint(1)\n```\n", encoding="utf-8"
    )
    assert window.open_path(document_path) is True
    code = card_id_of(window, "python")
    window.session.layouts[code].move_to(5000.0, 5000.0)

    document_path.write_text(
        "# Title\n\nintro\n\n### Section\n\n```python\nprint(1)\n```\n", encoding="utf-8"
    )
    assert window.session.refresh() is True

    assert window.session.layouts[code].x != 5000.0, "the level change rebuilds the board"
    assert "重建" in window.statusBar().currentMessage()


def test_acceptance_7_two_windows_are_independent(tmp_path: Path) -> None:
    document_path = tmp_path / "doc.md"
    shutil.copyfile(SAMPLE, document_path)
    first = MainWindow(persist=False)
    second = MainWindow(persist=False)
    assert first.open_path(document_path) is True
    assert second.open_path(document_path) is True

    code = card_id_of(first, "python")
    first.session.layouts[code].move_to(1234.0, 0.0)
    first.session.detach(code)

    assert second.session.layouts[code].x != 1234.0
    assert second.session.layouts[code].detached is False


def test_acceptance_8_a_restart_restores_the_stored_layout(tmp_path: Path) -> None:
    from mcwr.infrastructure.json_layout_store import JsonLayoutStore

    document_path = tmp_path / "doc.md"
    shutil.copyfile(SAMPLE, document_path)
    store = JsonLayoutStore(tmp_path / "appdata")
    first = MainWindow(persist=False, store=store, session_id="s", window_uuid="w")
    first.open_path(document_path)
    code = card_id_of(first, "python")
    # Attached cards are re-packed by the measured-height pass (T-049) and cannot be moved by the
    # user (T-043), so the arrangement that must survive a restart belongs to a movable card.
    first.session.detach(code)
    first.session.layouts[code].move_to(321.0, 654.0)
    assert first.session.persist() is True

    second = MainWindow(persist=False, store=store, session_id="s", window_uuid="w")
    second.open_path(document_path)
    assert (second.session.layouts[code].x, second.session.layouts[code].y) == (321.0, 654.0)


def test_acceptance_9_zoom_works_from_wheel_and_from_a_typed_value(window: MainWindow) -> None:
    open_sample(window)
    window.view.set_zoom(175.0)
    assert window.view.zoom_percent() == pytest.approx(175.0, abs=0.5)
    window.view.zoom_by(1.15)
    assert window.view.zoom_percent() > 175.0
    window.view.fit_cards()
    assert 10.0 <= window.view.zoom_percent() <= 800.0


def test_acceptance_10_broken_input_never_crashes_the_window(
    window: MainWindow, tmp_path: Path
) -> None:
    broken = tmp_path / "broken.md"
    broken.write_bytes(b"\xff\xfe\x00undefined bytes\x00\x81")
    opened = window.open_path(broken)
    status = window.statusBar().currentMessage()
    assert opened is True, "an undecodable file degrades, it does not abort the open"
    assert isinstance(status, str)

    empty = tmp_path / "empty.md"
    empty.write_text("", encoding="utf-8")
    assert window.open_path(empty) is True
    assert window.card_items == {}, "an empty document yields an empty board"

    weird = tmp_path / "weird.md"
    weird.write_text("```\nunclosed fence\n\n| broken | table\n", encoding="utf-8")
    assert window.open_path(weird) is True
