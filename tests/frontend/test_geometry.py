"""geometry: affine maps, and lengths, points, bounds and trimming of LIR paths."""

import math

import pytest

from irpipe.frontend import shapes
from irpipe.frontend.geometry import affine, curves
from irpipe.schema import lir

CIRCLE = shapes.ellipse((0, 0), 1, 1)
QUARTER = shapes.arc((0, 0), 1, 0, 90)
LINE = shapes.polyline(((0, 0), (2, 0)))


# Affine maps


def test_compose_applies_the_inner_map_first() -> None:
    scale, shift = affine.scaling(2, 3), affine.translation(1, 1)
    assert affine.apply(affine.compose(shift, scale), (1, 1)) == (3, 4)
    assert affine.apply(affine.compose(scale, shift), (1, 1)) == (4, 6)


def test_a_map_and_its_inverse_undo_each_other() -> None:
    turn = math.radians(30)
    m = (2 * math.cos(turn), 2 * math.sin(turn), -math.sin(turn), math.cos(turn), 3, -1)
    point = affine.apply(affine.invert(m), affine.apply(m, (0.5, 2)))
    assert point == pytest.approx((0.5, 2))


def test_a_flat_map_cannot_be_inverted() -> None:
    with pytest.raises(ValueError, match="flattens"):
        affine.invert((1, 0, 0, 0, 0, 0))


def test_a_turned_box_is_surrounded_by_a_larger_upright_box() -> None:
    quarter_turn = (0.0, 1.0, -1.0, 0.0, 0.0, 0.0)
    assert affine.transform_box(quarter_turn, (0, 0, 2, 1)) == pytest.approx((-1, 0, 0, 2))


# Lengths and points along a path


def test_lengths_are_measured_along_the_curve() -> None:
    assert curves.subpaths_length([CIRCLE]) == pytest.approx(2 * math.pi, rel=1e-3)
    assert curves.subpaths_length([LINE]) == 2


def test_a_point_along_a_path_is_by_length_with_its_direction() -> None:
    point, direction = curves.point_at([QUARTER], 0.5)
    half = math.sqrt(0.5)
    assert point == pytest.approx((half, half), abs=1e-3)
    assert direction == pytest.approx((-half, half), abs=1e-3)


def test_moving_to_the_next_subpath_adds_no_length() -> None:
    far = shapes.polyline(((10, 0), (12, 0)))
    point, _ = curves.point_at([LINE, far], 0.75)
    assert point == pytest.approx((11, 0))


def test_the_first_crossing_of_x_is_found_in_drawing_order() -> None:
    zigzag = shapes.polyline(((0, 0), (2, 2), (0, 4)))
    assert curves.crossing([zigzag], 1) == pytest.approx((1, 1))
    assert curves.crossing([zigzag], 3) is None


def test_ends_and_directions_of_an_arc() -> None:
    assert curves.end_point([QUARTER]) == pytest.approx((0, 1))
    assert curves.start_direction([QUARTER]) == pytest.approx((0, 1))
    assert curves.end_direction([QUARTER]) == pytest.approx((-1, 0))


def test_a_control_point_on_the_end_still_gives_a_direction() -> None:
    hooked = lir.Subpath(start=(0, 0), segments=(lir.CubicTo(cubic=((1, 0), (2, 0), (2, 0))),))
    assert curves.end_direction([hooked]) == pytest.approx((1, 0))


# Bounds, maps and trimming


def test_the_box_of_a_curve_is_exact_and_ignores_control_points() -> None:
    bump = lir.Subpath(start=(0, 0), segments=(lir.CubicTo(cubic=((0, 4), (2, 4), (2, 0))),))
    assert curves.bbox([bump]) == pytest.approx((0, 0, 2, 3))
    assert curves.bbox([CIRCLE]) == pytest.approx((-1, -1, 1, 1))


def test_a_map_moves_every_control_point() -> None:
    (moved,) = curves.transform([LINE], (2, 0, 0, 1, 1, 1))
    assert (moved.start, moved.segments[0]) == ((1, 1), lir.LineTo(line=(5, 1)))


def test_trimming_cuts_by_length_from_either_end() -> None:
    (cut,) = curves.trim([LINE], 0.5, 0.25)
    assert (cut.start, cut.segments) == ((0.5, 0), (lir.LineTo(line=(1.75, 0)),))
    (arc,) = curves.trim([QUARTER], 0.1, 0.1)
    assert curves.subpaths_length([arc]) == pytest.approx(math.pi / 2 - 0.2, abs=1e-3)


def test_trimming_more_than_the_path_leaves_a_tenth_of_it() -> None:
    (cut,) = curves.trim([LINE], 3, 0)
    assert curves.subpaths_length([cut]) == pytest.approx(0.2)


def test_a_closed_subpath_is_not_trimmed() -> None:
    assert curves.trim([CIRCLE], 0.5, 0.5) == (CIRCLE,)
