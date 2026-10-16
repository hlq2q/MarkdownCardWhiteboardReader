"""Snap a card's position onto the whiteboard grid (T-048).

The board paints a grid one title bar tall (22.7 px, ``theme.GRID_STEP``): a card dropped near
pulled onto it, so a board can be arranged on a tidy lattice without pixel hunting. The two axes are
decided on their own -- a drop that is close in x and far in y moves in x only, which is what a user
expects from a per-axis guide.
"""

from __future__ import annotations

GRID_STEP: float = 22.7
"""Grid pitch in scene units (one title bar); the painted grid and a test must agree (T-061)."""

SNAP_TOLERANCE: float = 12.0
"""How close a coordinate has to be to a grid line before it is pulled onto it."""


def snap_to_grid(
    x: float,
    y: float,
    *,
    step: float = GRID_STEP,
    tolerance: float = SNAP_TOLERANCE,
) -> tuple[float, float]:
    """Return ``(x, y)`` with each axis snapped when it is within ``tolerance`` of a line."""
    return (_snap_axis(x, step, tolerance), _snap_axis(y, step, tolerance))


def _snap_axis(value: float, step: float, tolerance: float) -> float:
    nearest = round(value / step) * step
    return nearest if abs(nearest - value) <= tolerance else value
