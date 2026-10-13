"""Unit tests for the grid snap (T-048)."""

from __future__ import annotations

from mcwr.application.features.layout_board.grid import (
    GRID_STEP,
    SNAP_TOLERANCE,
    snap_to_grid,
)


def test_a_position_already_on_the_grid_is_left_alone() -> None:
    assert snap_to_grid(120.0, 80.0, step=40.0) == (120.0, 80.0)


def test_a_position_within_tolerance_is_pulled_onto_the_line() -> None:
    spaced = snap_to_grid(120.0 + SNAP_TOLERANCE, 80.0 - SNAP_TOLERANCE, step=40.0)
    assert spaced == (120.0, 80.0)


def test_a_position_beyond_tolerance_keeps_its_place() -> None:
    off = SNAP_TOLERANCE + 0.001
    assert snap_to_grid(120.0 + off, 80.0 - off, step=40.0) == (120.0 + off, 80.0 - off)


def test_each_axis_is_decided_on_its_own() -> None:
    """Close in x, far in y: only x moves -- a diagonal-only snap would surprise the user."""
    assert snap_to_grid(123.0, 137.0, step=40.0) == (120.0, 137.0)


def test_negative_coordinates_snap_as_well() -> None:
    assert snap_to_grid(-118.0, -40.5, step=40.0) == (-120.0, -40.0)


def test_the_step_and_tolerance_can_be_overridden() -> None:
    assert snap_to_grid(23.0, 47.0, step=20.0) == (20.0, 40.0)
    assert snap_to_grid(23.0, 47.0, tolerance=2.0) == (23.0, 47.0)


def test_the_default_step_is_the_painted_grid() -> None:
    assert GRID_STEP == 34.0  # one title bar (T-061)
