"""GUI smoke tests on the offscreen Qt platform (acceptance 1, 4, 5, 6, 9)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from mcwr.interfaces.gui.main_window import MainWindow

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "spikes" / "samples" / "sample.md"


def card_id_of(window: MainWindow, title: str) -> str:
    document = window.session.document
    assert document is not None
    matches = [card.card_id for card in document.tree.cards.values() if card.title == title]
    assert len(matches) == 1, f"expected one card titled {title!r}"
    return matches[0]


@pytest.fixture
def window() -> MainWindow:
    return MainWindow(persist=False)


def test_opening_a_file_builds_one_item_per_card(window: MainWindow) -> None:
    assert window.open_path(SAMPLE) is True
    document = window.session.document
    assert document is not None
    assert len(window.card_items) == len(document.tree.cards)


def test_attached_cards_are_parented_to_their_card(window: MainWindow) -> None:
    window.open_path(SAMPLE)
    document = window.session.document
    assert document is not None
    for card_id, item in window.card_items.items():
        parent_id = document.tree.cards[card_id].parent_id
        if parent_id is None:
            assert item.parentItem() is None
        else:
            assert item.parentItem() is window.card_items[parent_id]


def test_every_card_is_placed_at_its_domain_coordinates(window: MainWindow) -> None:
    window.open_path(SAMPLE)
    for card_id, item in window.card_items.items():
        layout = window.session.layouts[card_id]
        position = item.scenePos()
        assert (round(position.x()), round(position.y())) == (round(layout.x), round(layout.y))


def test_drag_records_the_new_position(window: MainWindow) -> None:
    window.open_path(SAMPLE)
    code = card_id_of(window, "python")
    window.session.detach(code)  # only a free card accepts a drag (T-043)
    item = window.card_items[code]
    item.setPos(item.pos().x() + 120.0, item.pos().y() + 60.0)
    item.moved.emit(item, item.scenePos().x(), item.scenePos().y())
    assert window.session.layouts[code].x == pytest.approx(item.scenePos().x())


def test_detach_and_restore_change_parenting_and_state(window: MainWindow) -> None:
    window.open_path(SAMPLE)
    code = card_id_of(window, "python")

    window.session.detach(code)
    assert window.session.layouts[code].detached is True
    assert window.card_items[code].parentItem() is None, "a free card floats on the canvas"

    window.session.restore(code)
    assert window.session.layouts[code].detached is False
    assert window.card_items[code].parentItem() is not None


def test_top_level_card_cannot_be_detached(window: MainWindow) -> None:
    window.open_path(SAMPLE)
    document = window.session.document
    assert document is not None
    section = document.tree.root_ids[0]
    change = window.session.detach(section)
    assert change.changed is False
    assert window.session.layouts[section].detached is False


def test_folding_hides_descendants_and_unfolding_shows_them(window: MainWindow) -> None:
    window.open_path(SAMPLE)
    heading = card_id_of(window, "Table")
    table = card_id_of(window, "table")

    window.session.fold(heading)
    assert window.card_items[table].isVisible() is False

    window.session.fold(heading)
    assert window.card_items[table].isVisible() is True


def test_restore_all_returns_to_the_initial_arrangement(window: MainWindow) -> None:
    window.open_path(SAMPLE)
    code = card_id_of(window, "python")
    deep = card_id_of(window, "Mermaid")
    window.session.detach(code)
    window.session.fold(deep)

    window.session.restore_all()

    assert all(layout.detached is False for layout in window.session.layouts.values())
    assert all(layout.collapsed is False for layout in window.session.layouts.values())
    assert window.card_items[code].parentItem() is not None


def test_zoom_is_clamped_and_reported(window: MainWindow) -> None:
    window.open_path(SAMPLE)
    window.view.set_zoom(150.0)
    assert window.view.zoom_percent() == pytest.approx(150.0, abs=0.5)
    window.view.set_zoom(1000.0)
    assert window.view.zoom_percent() == pytest.approx(800.0, abs=0.5)
    window.view.set_zoom(0.001)
    assert window.view.zoom_percent() == pytest.approx(10.0, abs=0.5)
    window.view.zoom_by(1.25)
    assert window.view.zoom_percent() == pytest.approx(12.5, abs=0.5)


def test_refresh_keeps_positions_and_adds_new_cards(window: MainWindow, tmp_path: Path) -> None:
    """A card added without touching heading levels keeps every existing position."""
    document_copy = tmp_path / "doc.md"
    shutil.copyfile(SAMPLE, document_copy)
    assert window.open_path(document_copy) is True
    code = card_id_of(window, "python")
    # A card inside its parent cannot be moved (T-043/D-050), so mark an arrangement the app can
    # really produce: detach the card first, then place it (T-049 re-packs attached cards).
    window.session.detach(code)
    window.session.layouts[code].move_to(4242.0, 2424.0)
    cards_before = len(window.session.document.tree.cards)  # type: ignore[union-attr]

    with document_copy.open("a", encoding="utf-8") as handle:
        handle.write("\n- [ ] an added task\n")
    before_mtime = document_copy.stat().st_mtime_ns

    assert window.session.refresh() is True

    document = window.session.document
    assert document is not None
    assert window.session.layouts[code].x == 4242.0, "existing layout must survive a refresh"
    assert len(document.tree.cards) == cards_before + 1, "the task list became a new card"
    assert document_copy.stat().st_mtime_ns == before_mtime, "refresh must not write to the file"


def test_a_major_structural_change_rebuilds_the_board(window: MainWindow, tmp_path: Path) -> None:
    """D11: a new divider changes the big-section count, so the layout is rebuilt."""
    document_copy = tmp_path / "doc.md"
    shutil.copyfile(SAMPLE, document_copy)
    assert window.open_path(document_copy) is True
    code = card_id_of(window, "python")
    window.session.layouts[code].move_to(5000.0, 5000.0)

    with document_copy.open("a", encoding="utf-8") as handle:
        handle.write("\n---\n\n## Whole new section\n\nbody\n")

    assert window.session.refresh() is True

    document = window.session.document
    assert document is not None
    assert len(document.tree.root_ids) == 2, "the sample's H1 plus the appended one"
    assert window.session.layouts[code].x != 5000.0, "a major change rebuilds the arrangement"
    assert "重建" in window.statusBar().currentMessage()


def test_layout_survives_a_restart(tmp_path: Path) -> None:
    """Acceptance 8: closing and reopening restores the layout from the app data dir."""
    from mcwr.infrastructure.json_layout_store import JsonLayoutStore

    document_copy = tmp_path / "doc.md"
    shutil.copyfile(SAMPLE, document_copy)
    store = JsonLayoutStore(tmp_path / "appdata")

    first = MainWindow(persist=False, store=store, session_id="s1", window_uuid="w1")
    assert first.open_path(document_copy) is True
    code = card_id_of(first, "python")
    first.session.layouts[code].move_to(1234.0, 567.0)
    first.session.detach(code)
    assert first.session.persist() is True

    second = MainWindow(persist=False, store=store, session_id="s1", window_uuid="w1")
    assert second.open_path(document_copy) is True

    assert second.session.layouts[code].x == 1234.0
    assert second.session.layouts[code].y == 567.0
    assert second.session.layouts[code].detached is True
    assert second.card_items[code].parentItem() is None


def test_a_new_session_does_not_share_the_previous_layout(tmp_path: Path) -> None:
    """Decision D15: sessions are independent; a new window seeds a copy of its own."""
    from mcwr.infrastructure.json_layout_store import JsonLayoutStore

    document_copy = tmp_path / "doc.md"
    shutil.copyfile(SAMPLE, document_copy)
    store = JsonLayoutStore(tmp_path / "appdata")

    first = MainWindow(persist=False, store=store, session_id="session-a", window_uuid="w1")
    first.open_path(document_copy)
    code = card_id_of(first, "python")
    # Only a card the user can move carries a personal arrangement (T-043/T-049): detach first.
    first.session.detach(code)
    first.session.layouts[code].move_to(999.0, 999.0)
    first.session.persist()

    second = MainWindow(persist=False, store=store, session_id="session-b", window_uuid="w2")
    second.open_path(document_copy)
    second.session.detach(code)
    second.session.layouts[code].move_to(1.0, 2.0)
    second.session.persist()

    third = MainWindow(persist=False, store=store, session_id="session-a", window_uuid="w1")
    third.open_path(document_copy)
    assert third.session.layouts[code].x == 999.0, "session A must keep its own layout"


def test_the_window_title_uses_the_product_display_name() -> None:
    """D-026 / T-030: one user-facing display name, kept in sync with the AppName folder."""
    from mcwr import PRODUCT_NAME
    from mcwr.infrastructure.app_paths import APP_DIR_NAME

    assert PRODUCT_NAME == APP_DIR_NAME, (
        "the display name must equal the %APPDATA% folder name (D-026)"
    )

    window = MainWindow(persist=False)
    assert window.windowTitle() == PRODUCT_NAME
    assert window.open_path(SAMPLE) is True
    assert window.windowTitle() == f"{SAMPLE.name} — {PRODUCT_NAME}"
