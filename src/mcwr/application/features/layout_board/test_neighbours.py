"""Unit tests for the neighbour-first snapping (T-051/D-052)."""

from __future__ import annotations

from mcwr.application.features.layout_board.grid import GRID_STEP
from mcwr.application.features.layout_board.neighbours import snap_delta

MOVING = (200.0, 300.0, 100.0, 50.0)
"""The dragged card: x 200..300, y 300..350."""


def test_nothing_nearby_falls_back_to_the_grid() -> None:
    """No neighbour at all: the 40 px grid still applies (D-051)."""
    dx, dy = snap_delta(MOVING, [])
    assert dx == 0.0
    assert dy == 0.0

    near_line = (203.0, 308.0, 100.0, 50.0)
    dx, dy = snap_delta(near_line, [])
    assert dx == -3.0  # 203 is 3 px past the 200 line
    assert dy == 12.0  # 308 is exactly the tolerance below the 320 line


def test_an_edge_within_the_tolerance_is_pulled_onto_the_neighbour() -> None:
    """The moving card's left edge meets the neighbour's right edge (adjacency)."""
    neighbour = (300.0, 500.0, 120.0, 50.0)  # right edge at 420
    box = (414.0, 500.0, 100.0, 50.0)  # left edge 6 px away
    dx, dy = snap_delta(box, [neighbour])
    assert dx == 6.0
    assert dy == 0.0  # y 500 is already on the grid


def test_an_edge_further_than_the_tolerance_keeps_its_place() -> None:
    neighbour = (300.0, 500.0, 120.0, 50.0)  # right edge at 420
    box = (460.0, 300.0, 100.0, 50.0)  # 40 px from that edge and 20 px from any grid line
    dx, dy = snap_delta(box, [neighbour])
    assert dx == 0.0
    assert dy == 0.0


def test_edges_win_over_the_grid() -> None:
    """Both are close: the neighbour decides, not the grid line."""
    neighbour = (300.0, 500.0, 108.0, 50.0)  # right edge at 408
    box = (403.0, 500.0, 100.0, 50.0)  # 5 px from the edge, 3 px from the 400 grid line
    dx, _ = snap_delta(box, [neighbour])
    assert dx == 5.0  # onto 408, not back onto 400


def test_each_axis_is_decided_on_its_own() -> None:
    """Close horizontally, far vertically: only x moves."""
    neighbour = (300.0, 900.0, 130.0, 50.0)
    box = (425.0, 300.0, 100.0, 50.0)
    dx, dy = snap_delta(box, [neighbour])
    assert dx == 5.0  # left edge onto the neighbour's right edge at 430
    assert dy == 0.0  # 300 is on the grid and no neighbour edge is near


def test_the_closest_candidate_wins() -> None:
    """Two neighbours within reach: the smaller shift is taken."""
    far = (600.0, 0.0, 100.0, 10.0)  # left edge 600, moving right edge is 300 -> +300, out of range
    near = (306.0, 0.0, 100.0, 10.0)  # left edge 306, moving right edge 300 -> +6
    closer = (297.0, 0.0, 100.0, 10.0)  # left edge 297, moving right edge 300 -> -3
    dx, _ = snap_delta(MOVING, [far, near, closer])
    assert dx == -3.0


def test_the_tolerance_and_step_can_be_overridden() -> None:
    neighbour = (500.0, 0.0, 100.0, 10.0)
    box = (497.0, 23.0, 100.0, 10.0)
    dx, dy = snap_delta(box, [neighbour], tolerance=5.0, step=20.0)
    assert dx == 3.0  # right edge 597 -> onto 600
    assert dy == -3.0  # 23 -> onto the 20 line


def test_the_default_step_is_the_painted_grid() -> None:
    assert GRID_STEP == 40.0
