"""How a dragged card, or a group of them, settles against the other cards (T-051/D-052).

Edges first, grid second: an edge of the moved box that lands within ``tolerance`` of another card's
edge is pulled onto it, and only when neither edge is near does the 40 px grid from D-051 apply. The
two axes are decided on their own, so a drop can line its left edge up with a neighbour's right edge
while keeping the y it had.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from mcwr.application.features.layout_board.grid import GRID_STEP, SNAP_TOLERANCE

Box = tuple[float, float, float, float]
"""A card's rectangle as ``(x, y, width, height)`` in scene units."""

_Edge = tuple[float, float]


def snap_delta(
    box: Box,
    others: Iterable[Box],
    *,
    tolerance: float = SNAP_TOLERANCE,
    step: float = GRID_STEP,
) -> tuple[float, float]:
    """Return the ``(dx, dy)`` that settles ``box`` against ``others``, else onto the grid."""
    neighbours = list(others)
    dx = _edge_delta((box[0], box[0] + box[2]), [_horizontal(o) for o in neighbours], tolerance)
    if dx is None:
        dx = _grid_delta(box[0], step, tolerance)
    dy = _edge_delta((box[1], box[1] + box[3]), [_vertical(o) for o in neighbours], tolerance)
    if dy is None:
        dy = _grid_delta(box[1], step, tolerance)
    return dx, dy


def _horizontal(box: Box) -> _Edge:
    return box[0], box[0] + box[2]


def _vertical(box: Box) -> _Edge:
    return box[1], box[1] + box[3]


def _edge_delta(moving: _Edge, targets: Sequence[_Edge], tolerance: float) -> float | None:
    """The smallest shift that puts one of ``moving``'s edges onto one of the targets' edges."""
    best: float | None = None
    for edge in moving:
        for target in targets:
            for candidate in (target[0] - edge, target[1] - edge):
                if abs(candidate) <= tolerance and (best is None or abs(candidate) < abs(best)):
                    best = candidate
    return best


def _grid_delta(edge: float, step: float, tolerance: float) -> float:
    nearest = round(edge / step) * step
    return nearest - edge if abs(nearest - edge) <= tolerance else 0.0
