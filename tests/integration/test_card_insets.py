"""The body element sits evenly inside its card: equal inset on all four sides (T-053).

The header bar used to sit directly on top of the body. Measured on a code card, the element was
10 px from the left and right edges (PADDING plus the document's own margin) but only 4 px from the
top and 16 px from the bottom, and a table card measured the same. Insetting the body by PADDING at
the top as well makes all four 10 px, because the document's own 4 px margin then lands the same way
on every side.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from mcwr.interfaces.gui.main_window import MainWindow

DOCUMENT = """# Code card

```python
a = 1
b = 2
c = 3
```

# Table card

| a | b | c |
| --- | --- | --- |
| 1 | 2 | 3 |
| 4 | 5 | 6 |

# Text card

one short line

# List card

- first
- second
"""


class StubRenderer:
    last_error = None

    def render(
        self, *, kind: object, source: str, scale: float, theme: str = "light"
    ) -> Path | None:
        del kind, source, scale, theme
        return None


@pytest.fixture
def window(tmp_path: Path) -> MainWindow:
    document = tmp_path / "insets.md"
    document.write_text(DOCUMENT, encoding="utf-8")
    window = MainWindow(persist=False, renderer=StubRenderer())  # type: ignore[arg-type]
    window.resize(1400, 1000)
    window.show()
    assert window.open_path(document) is True
    app = QApplication.instance()
    assert app is not None
    app.processEvents()
    return window


def test_every_body_sits_evenly_inside_its_card(window: MainWindow) -> None:
    """Code and table elements fill the body width, so all four distances are comparable.

    Lists and paragraphs report only their text extent, not the full body width, and a
    rendered-image body is drawn straight into the body rect -- both are checked elsewhere.
    """
    document = window.session.document
    assert document is not None
    checked = 0
    for card_id, item in window.card_items.items():
        card = document.tree.cards[card_id]
        if card.kind not in (CardKind.CODE, CardKind.TABLE):
            continue
        left, right, top, bottom = item.body_insets()
        assert left > 0.0, card.title
        assert right == pytest.approx(left, abs=1.0), card.title
        assert top == pytest.approx(left, abs=1.0), card.title
        assert bottom == pytest.approx(left, abs=1.0), card.title
        checked += 1
    assert checked >= 2, "the code and table cards must both be measured"
