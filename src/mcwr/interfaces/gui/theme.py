"""The visual spec as data: two palettes, the fonts and the metrics (T-024, D-021/D-030).

``docs/visual-spec.md`` is the single source of every number in this module — the 16
semantic colour slots, the font families, the metrics and the dark-mode rules. Nothing here
is invented locally, and ``test_theme.py`` re-checks the spec's own constraints (every slot
present, no pure black, no pure white, WCAG AA contrast) so a value that drifts away from
the spec fails a test instead of shipping.

Qt is imported in exactly one place — :func:`system_is_dark` — so the palette itself stays
importable, and testable, without a ``QApplication``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, cast

from mcwr.domain.enums import CardKind

PT_PER_PX: Final[float] = 0.75
"""Qt sizes are points (1/72 inch), the spec's sizes are CSS pixels: 1 px = 0.75 pt."""

GRID_STEP: Final[float] = 22.7
"""Grid pitch: one title bar, so the lines land on the header edges (T-061)."""
GRID_ALPHA: Final[int] = 102
"""The spec's grid is ``divider`` at 40% opacity: round(0.40 * 255)."""

SHADOW_RGBA: Final[tuple[int, int, int, int]] = (15, 23, 42, 20)
"""Light-theme card shadow ``rgba(15,23,42,0.08)``; the dark theme draws none (§4)."""


class Theme(StrEnum):
    """A resolved theme: exactly one of the two palettes is in use."""

    LIGHT = "light"
    DARK = "dark"


class ThemeMode(StrEnum):
    """What the user picked; ``SYSTEM`` defers to the Windows app theme (D-030)."""

    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


@dataclass(frozen=True, slots=True)
class Palette:
    """The 16 semantic slots of one theme, exactly as named in the visual spec §1."""

    theme: Theme
    app_bg: str
    board_bg: str
    big_card_bg: str
    heading_card_bg: str
    card_bg: str
    code_bg: str
    table_bg: str
    text_primary: str
    text_secondary: str
    link: str
    card_edge: str
    border: str
    divider: str
    selected: str
    hover: str
    drag: str
    error_text: str
    error_bg: str
    pygments_style: str
    """Pygments style name for code cards (T-029): a style name, not a colour slot."""
    level_bar: tuple[str, str, str, str]
    """The 4 depth-bar tiers of visual spec §6.1 (outermost … 4th level and deeper)."""


LIGHT: Final[Palette] = Palette(
    theme=Theme.LIGHT,
    app_bg="#F3F5F7",
    board_bg="#E3E8EE",
    big_card_bg="#F7F9FC",
    heading_card_bg="#F1F6FD",
    card_bg="#FDFDFE",
    code_bg="#F1F4F7",
    table_bg="#FDFDFE",
    text_primary="#1F2733",
    text_secondary="#55606D",
    link="#1B5FA8",
    card_edge="#7A8592",
    border="#C7D0DA",
    divider="#C9D3DD",
    selected="#1B6FD6",
    hover="#E8F0FA",
    drag="#D6E7FF",
    error_text="#B3261E",
    error_bg="#FCEEEE",
    pygments_style="default",
    level_bar=("#D0D7DE", "#AFB8C1", "#8C959F", "#6E7781"),
)
"""Light theme: no pure white — the card fill is ``#FDFDFE`` and body text ``#1F2733``."""

DARK: Final[Palette] = Palette(
    theme=Theme.DARK,
    app_bg="#1B1F24",
    board_bg="#191D22",
    big_card_bg="#262C34",
    heading_card_bg="#2C333C",
    card_bg="#2A3038",
    code_bg="#20252B",
    table_bg="#2A3038",
    text_primary="#E6EAF0",
    text_secondary="#A8B2BF",
    link="#7DB4FF",
    card_edge="#7E8896",
    border="#3C4550",
    divider="#3C4550",
    selected="#6FA8FF",
    hover="#333B45",
    drag="#3A4A63",
    error_text="#FF9A93",
    error_bg="#3A2523",
    pygments_style="monokai",
    level_bar=("#30363D", "#484F58", "#6E7681", "#8B949E"),
)
"""Dark theme: no pure black — backgrounds are ``#191D22``/``#1B1F24``, text ``#E6EAF0``."""

PALETTES: Final[dict[Theme, Palette]] = {Theme.LIGHT: LIGHT, Theme.DARK: DARK}

# ---------------------------------------------------------------------------- fonts

UI_FONT: Final[str] = "Segoe UI"
UI_FONT_FALLBACK: Final[str] = "Microsoft YaHei UI"
HEADING_FONT: Final[str] = "Segoe UI Semibold"
CODE_FONT: Final[str] = "Cascadia Mono"
CODE_FONT_FALLBACK: Final[str] = "Consolas"

FONT_PX: Final[dict[str, float]] = {
    "h1": 28.0,
    "h2": 24.0,
    "h3": 20.0,
    "h4": 17.0,
    "h5": 15.0,
    "h6": 14.0,
    "body": 14.0,
    "code": 13.0,
    "table": 13.0,
    "task_list": 14.0,
    "toc": 13.0,
    "control": 12.5,
}
"""Spec §2. ``control`` is the UI size and also the card header bar size."""

# -------------------------------------------------------------------------- metrics

HEADER_HEIGHT: Final[float] = 22.7
PADDING: Final[float] = 6.0
CARD_RADIUS: Final[float] = 8.0
BUTTON_RADIUS: Final[float] = 6.0
SELECTED_WIDTH: Final[float] = 2.5
BORDER_WIDTH: Final[float] = 1.0
CARD_GAP: Final[float] = 16.0
SECTION_GAP: Final[float] = 24.0
CHILD_INDENT: Final[float] = 24.0
MIN_BODY_HEIGHT: Final[float] = 24.0
LEVEL_BAR_WIDTH: Final[float] = 3.0
"""Width of the left depth stripe (visual spec §6.1)."""
LEVEL_BAR_TIERS: Final[int] = 4
"""Distinct depth buckets; the 5th level and deeper reuse the last one (D-032)."""
MIN_LEGIBLE_ON_SCREEN_WIDTH: Final[float] = 160.0
"""Below this on-screen width (logical px) a card counts as a thumbnail: T-031 does not rasterize
its rich body, because at that size a formula bitmap is as unreadable as its source text and
rendering it would only queue work. T-033 briefly reused this floor for card painting and the
measurement showed that was the wrong lever (see D-042) — the name is kept because it says what
the number means, not which feature happens to use it."""


def points(px: float) -> float:
    """Convert a spec pixel size to the Qt point size used by ``QFont``."""
    return px * PT_PER_PX


def palette_for(theme: Theme) -> Palette:
    """The palette of ``theme`` (the only way call sites should reach a palette)."""
    return PALETTES[theme]


def resolve_theme(mode: ThemeMode, *, system_dark: bool) -> Theme:
    """Turn the user's mode plus the current system scheme into a concrete theme (D-030)."""
    if mode is ThemeMode.SYSTEM:
        return Theme.DARK if system_dark else Theme.LIGHT
    return Theme(mode.value)


def system_is_dark() -> bool:
    """Whether Windows currently reports a dark app theme.

    ``QStyleHints.colorScheme()`` exists since Qt 6.5; a Qt without it (or without a
    ``QGuiApplication``) simply answers "not dark", which resolves ``SYSTEM`` to light
    instead of failing.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication

    existing = QGuiApplication.instance()
    if existing is None:
        return False
    # ``instance()`` is typed as QCoreApplication; a GUI run only ever has the QGuiApplication.
    app = cast(QGuiApplication, existing)
    scheme = getattr(app.styleHints(), "colorScheme", None)
    if not callable(scheme):
        return False
    return bool(scheme() == Qt.ColorScheme.Dark)


def content_palette(palette: Palette, kind: CardKind) -> Palette:
    """The palette a card's *content* is drawn with.

    The same as ``palette`` except for ``[TOC]``, whose dark fill would swallow the light theme's
    dark text: its header, body text, links and code all come from ``DARK`` so the card stays
    readable in both themes (T-074).
    """
    return DARK if kind is CardKind.TOC else palette


def card_fill(palette: Palette, kind: CardKind) -> str:
    """The fill of one card kind (spec §1: heading, code/image, table, rest).

    ``[TOC]`` is deliberately the *dark* fill in both themes (T-074): the table of contents is a
    navigation surface, and the user asked for it to read as dark whatever the theme is.
    """
    if kind is CardKind.TOC:
        return DARK.card_bg
    if kind is CardKind.HEADING:
        return palette.heading_card_bg
    if kind is CardKind.CODE or kind is CardKind.IMAGE:
        return palette.code_bg
    if kind is CardKind.TABLE:
        return palette.table_bg
    return palette.card_bg


def uses_shadow(theme: Theme) -> bool:
    """Spec §4: the light theme shadows cards, the dark theme uses a 1 px border instead."""
    return theme is Theme.LIGHT


def level_bar_colour(palette: Palette, depth: int) -> str:
    """Colour of the left depth stripe for a card at ``depth`` (0 = outermost card).

    The spec's tier 1 is "最外层 / 大卡片", so ``depth`` selects the tier directly and any
    level from the 4th on clamps to the last bucket (no further darkening or lightening).
    """
    tier = min(max(depth, 0), LEVEL_BAR_TIERS - 1)
    return palette.level_bar[tier]
