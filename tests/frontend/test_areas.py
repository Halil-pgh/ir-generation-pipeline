"""geometry: areas with both fill rules, half planes, graph areas, flood fill and clipping."""

import math

import pytest
from shapely.geometry import LineString, Point

from irpipe.frontend import shapes
from irpipe.frontend.geometry import areas, curves
from irpipe.frontend.geometry.clip import clip_fill, clip_stroke
from irpipe.frontend.geometry.flood import FloodError, flood
from irpipe.schema import lir

BIG = shapes.ellipse((0, 0), 2, 2)
SMALL = shapes.ellipse((0, 0), 1, 1)
REVERSED_SMALL = curves.subpath_of(
    [tuple(reversed(piece)) for piece in reversed(curves.pieces(SMALL))], closed=True
)


# Areas and fill rules


def test_even_odd_leaves_a_hole_and_nonzero_fills_it_when_both_turn_alike() -> None:
    assert areas.area([BIG, SMALL], "evenodd").area == pytest.approx(3 * math.pi, rel=1e-3)
    assert areas.area([BIG, SMALL], "nonzero").area == pytest.approx(4 * math.pi, rel=1e-3)


def test_nonzero_leaves_a_hole_where_the_inner_subpath_turns_the_other_way() -> None:
    assert areas.area([BIG, REVERSED_SMALL], "nonzero").area == pytest.approx(3 * math.pi, rel=1e-3)


def test_a_lone_clockwise_subpath_is_filled() -> None:
    clockwise = curves.subpath_of(
        [tuple(reversed(piece)) for piece in reversed(curves.pieces(BIG))], closed=True
    )
    assert areas.area([clockwise]).area == pytest.approx(4 * math.pi, rel=1e-3)


def test_an_area_comes_back_as_subpaths_with_one_per_hole() -> None:
    ring = areas.subpaths(areas.area([BIG, SMALL], "evenodd"))
    assert len(ring) == 2 and all(s.closed for s in ring)
    assert areas.area(ring, "evenodd").area == pytest.approx(3 * math.pi, rel=1e-3)


def test_lines_come_back_as_open_subpaths() -> None:
    (piece,) = areas.subpaths(LineString([(0, 0), (1, 1), (2, 0)]))
    assert (piece.start, piece.closed, len(piece.segments)) == ((0, 0), False, 2)


def test_a_half_plane_is_left_of_its_line() -> None:
    plane = areas.half_plane((0, 0), (1, 0), (-8, -4.5, 8, 4.5))
    assert plane.contains(Point(3, 2)) and not plane.contains(Point(3, -2))


def test_under_and_between_graphs() -> None:
    rising = [(0.0, 0.0), (2.0, 2.0)]
    assert areas.under(rising).area == pytest.approx(2)
    assert areas.between([(0.0, 3.0), (2.0, 3.0)], rising).area == pytest.approx(4)


def test_a_graph_that_crosses_zero_gives_both_lobes() -> None:
    assert areas.under([(-1.0, -1.0), (1.0, 1.0)]).area == pytest.approx(1)


# Flood fill


def parabola() -> LineString:
    return LineString([(x / 20, 0.5 * (x / 20 - 1) ** 2) for x in range(-20, 61)])


LINE = LineString([(-1, 1.5), (3, 1.5)])
WALL = LineString([(2.5, -1), (2.5, 3)])


def test_the_seed_fills_the_face_its_lines_close() -> None:
    face = flood([parabola(), LINE, WALL], (1.2, 0.4))
    assert face.area == pytest.approx(3.4196, rel=1e-3)  # the integral of 1.5 - (x-1)^2/2


def test_a_seed_on_a_line_says_which_line() -> None:
    with pytest.raises(FloodError) as caught:
        flood([parabola(), LINE, WALL], (1.0, 1.5))
    assert caught.value.on == 1


def test_lines_that_leave_the_seed_open_are_refused() -> None:
    with pytest.raises(FloodError, match="do not close"):
        flood([parabola(), LINE], (1.2, 5))


def test_a_closed_line_inside_the_face_leaves_a_hole() -> None:
    rings = [areas.lines([BIG]), areas.lines([SMALL])]
    face = flood(rings, (1.5, 0))
    assert face.area == pytest.approx(3 * math.pi, rel=1e-3)


# Clipping


def test_a_fill_wholly_inside_the_mask_is_kept_as_it_is() -> None:
    mask = areas.area([BIG])
    assert clip_fill([SMALL], "nonzero", mask) == ((SMALL,), "nonzero")
    assert clip_stroke([SMALL], mask) == (SMALL,)


def test_a_fill_partly_outside_is_cut_to_the_mask() -> None:
    square = shapes.rect((1, 0), 2, 2, 0)
    inside, rule = clip_fill([square], "nonzero", areas.area([SMALL]))
    assert rule == "evenodd"
    assert areas.area(inside, rule).area == pytest.approx(math.pi / 2, rel=1e-3)


def test_a_line_through_the_mask_is_cut_where_the_mask_ends() -> None:
    (cut,) = clip_stroke([shapes.polyline(((-2, 0), (2, 0)))], areas.area([SMALL]))
    last = cut.segments[-1]
    assert isinstance(last, lir.LineTo)
    assert cut.start == pytest.approx((-1, 0), abs=1e-3)
    assert last.line == pytest.approx((1, 0), abs=1e-3)
