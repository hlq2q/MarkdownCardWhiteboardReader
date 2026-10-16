"""The manual functional test-case document parses into every card kind.

``spikes/samples/functional-test.md`` is the file a human walks through to check the app by hand;
this test keeps it honest: it must open without warnings and keep covering all eight card kinds, so
a feature that stops being reachable from the document is noticed here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from mcwr.domain.enums import CardKind
from mcwr.interfaces.gui.main_window import MainWindow
from mcwr.interfaces.gui.theme import HEADER_HEIGHT, PADDING

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "spikes" / "samples" / "functional-test.md"


class StubRenderer:
    last_error = None

    def render(
        self, *, kind: object, source: str, scale: float, theme: str = "light"
    ) -> Path | None:
        del kind, source, scale, theme
        return None


@pytest.fixture
def window() -> MainWindow:
    window = MainWindow(persist=False, renderer=StubRenderer())  # type: ignore[arg-type]
    window.resize(1200, 900)
    window.show()
    assert window.open_path(SAMPLE) is True
    app = QApplication.instance()
    assert app is not None
    app.processEvents()
    return window


def test_the_functional_sample_opens_without_warnings(window: MainWindow) -> None:
    loaded = window.session.document
    assert loaded is not None
    assert loaded.warnings == ()
    assert window.session.card_count >= 60, "the file is meant to be a full board"


def test_the_functional_sample_covers_every_card_kind(window: MainWindow) -> None:
    loaded = window.session.document
    assert loaded is not None
    kinds = {card.kind for card in loaded.tree.cards.values()}
    assert kinds == set(CardKind), "every card kind must be reachable from this document"


def test_the_functional_sample_has_no_wrapper_card(window: MainWindow) -> None:
    """T-055: the roots are the document's own top-level headings."""
    loaded = window.session.document
    assert loaded is not None
    roots = [loaded.tree.cards[root_id] for root_id in loaded.tree.root_ids]
    assert [card.kind for card in roots] == [CardKind.FALLBACK_TEXT, CardKind.HEADING]
    assert roots[0].title == "text", "content before the first heading is a card of its own"
    assert roots[1].title.startswith("功能测试用例")


def test_the_long_table_and_the_code_card_fit_their_content(window: MainWindow) -> None:
    """E-029: a 25-row table and a 35-line code block must not be clipped or padded."""
    loaded = window.session.document
    assert loaded is not None
    checked: dict[str, float] = {}
    for card_id, item in window.card_items.items():
        card = loaded.tree.cards[card_id]
        measured = item.measured_body_height()
        if measured is None or card.child_ids:
            continue
        if card.kind is CardKind.TABLE and card.title == "table":
            checked["table"] = item.card_height - measured
        if card.kind is CardKind.CODE:
            checked["code"] = item.card_height - measured
    assert checked, "the sample must contain a table and a code card"
    # header + two paddings above the measured body, i.e. nothing clipped and nothing extra
    reserve = HEADER_HEIGHT + 2 * PADDING
    # Not clipped: the body keeps at least its measured height; nothing extra: at most the
    # reserved header+paddings plus the few px the re-measure can drift (T-076).
    for name, slack in checked.items():
        assert slack >= reserve - 1.0, f"{name} body is clipped"
        assert slack <= reserve + 6.0, f"{name} card reserves more than its header+paddings"
