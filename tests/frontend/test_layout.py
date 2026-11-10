"""layout: box points, placing beside a point or a box, and grids."""

import math

import pytest

from irpipe.frontend import layout


@pytest.mark.parametrize(
    ("anchor", "point"),
    [
        ("center", (1, 1)),
        ("left_top", (0, 2)),
        ("right_bottom", (2, 0)),
        ("center_baseline", (1, 0.5)),
    ],
)
def test_the_points_of_a_box(anchor: str, point: tuple[float, float]) -> None:
    assert layout.box_point((0, 0, 2, 2), anchor, baseline=0.5) == point


def test_a_baseline_point_needs_a_baseline() -> None:
    with pytest.raises(ValueError, match="needs a baseline"):
        layout.box_point((0, 0, 2, 2), "left_baseline")


@pytest.mark.parametrize(
    ("direction", "vector"),
    [
        ("up", (0, 1)),
        ("down_left", (-math.sqrt(0.5), -math.sqrt(0.5))),
        (90.0, (0, 1)),
        ((3.0, 4.0), (0.6, 0.8)),
    ],
)
def test_a_direction_is_a_name_an_angle_or_a_vector(
    direction: str | float | tuple[float, float], vector: tuple[float, float]
) -> None:
    assert layout.unit_vector(direction) == pytest.approx(vector)  # type: ignore[arg-type]


def test_beside_a_point_the_gap_is_measured_to_the_nearest_edge() -> None:
    assert layout.beside((0, 0, 0, 0), (1, 0), 0.5, 2, 1) == pytest.approx((1.5, 0))
    assert layout.beside((0, 0, 0, 0), (0, -1), 0.5, 2, 1) == pytest.approx((0, -1))


def test_beside_a_box_on_a_diagonal_the_boxes_keep_the_gap_along_the_ray() -> None:
    u = layout.unit_vector("up_right")
    center = layout.beside((-1, -1, 1, 1), u, 0, 2, 2)
    assert center == pytest.approx((2, 2))  # corner to corner


def test_a_column_is_as_wide_as_its_widest_child() -> None:
    grid = layout.grid([(2, 1, 0), (4, 1, 0)], 1, (0, 0.5), on_baselines=False)
    assert grid.cells == ((0, -1, 4, 0), (0, -2.5, 4, -1.5))
    assert grid.box == (0, -2.5, 4, 0)


def test_a_row_on_its_baselines_is_tall_enough_for_both_extremes() -> None:
    grid = layout.grid([(1, 2, 0), (1, 1, 1)], 2, (0.5, 0), on_baselines=True)
    assert grid.cells == ((0, -3, 1, 0), (1.5, -3, 2.5, 0))
    assert grid.baselines == (-2, -2)


def test_a_grid_fills_rows_left_to_right() -> None:
    grid = layout.grid([(1, 1, 0)] * 3, 2, (0, 0), on_baselines=False)
    assert [cell[:2] for cell in grid.cells] == [(0, -1), (1, -1), (0, -2)]
    assert grid.box == (0, -2, 2, 0)
