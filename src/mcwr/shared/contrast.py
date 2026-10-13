"""WCAG 2.1 contrast maths, shared by the palette and the syntax highlighter.

Pure functions: no Qt, no IO, no state. They live in ``shared`` because two layers need the
same numbers — ``interfaces/gui/theme.py`` (the visual spec's contrast table) and
``infrastructure/pygments_highlighter.py`` (which must drop a token colour that is not
readable on the code background) — and neither should import the other.
"""

from __future__ import annotations

from typing import Final

MIN_RATIO_AA: Final[float] = 4.5
"""WCAG AA for body text (the threshold the visual spec cites)."""

MIN_RATIO_NON_TEXT: Final[float] = 3.0
"""WCAG AA for large text, edges and UI states (the spec's card edge / selection floor)."""


def relative_luminance(color: str) -> float:
    """WCAG 2.1 relative luminance of an ``#RRGGBB`` colour."""
    channels: list[float] = []
    for offset in (1, 3, 5):
        raw = int(color[offset : offset + 2], 16) / 255.0
        channels.append(raw / 12.92 if raw <= 0.03928 else ((raw + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG 2.1 contrast ratio between two ``#RRGGBB`` colours (1.0 … 21.0)."""
    first = relative_luminance(foreground)
    second = relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)
