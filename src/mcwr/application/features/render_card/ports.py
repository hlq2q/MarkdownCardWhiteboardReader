"""Ports of the render_card slice (implemented by infrastructure adapters)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from mcwr.domain.enums import CardKind


class WebCardRenderer(Protocol):
    """Rasterizes the card kinds a text document cannot draw (D14, R2).

    The whiteboard is scaled by a single canvas transform (D7), so a live web widget
    cannot be used: the implementation renders **offscreen** and hands back a PNG that
    the canvas draws as a static pixmap, so zoom stays crisp and hit-testing unaffected.
    """

    def render(self, *, kind: CardKind, source: str, scale: float) -> Path | None:
        """Return a cached PNG for this content at this zoom, or None if rendering is impossible.

        ``scale`` is the canvas zoom (1.0 = 100%); the renderer rounds it to its own
        bucket step. Implementations never raise: every failure (missing assets, no
        WebEngine, timeout, blank grab) degrades to ``None`` so the caller keeps its
        text fallback.
        """
        ...
