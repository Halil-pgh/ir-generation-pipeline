"""The script's geometry: exact while the answer is rational, floats after that."""

import math
from fractions import Fraction as Frac

import pytest
from shapely import Point, Polygon

from irpipe.irkit import geometry as g
from irpipe.irkit import smooth, through


def test_the_tangents_from_5_0_touch_the_circle_of_radius_3_exactly() -> None:
    first, second = g.tangent_points((5, 0), (0, 0), 3)
    assert (first, second) == ((Frac(9, 5), Frac(12, 5)), (Frac(9, 5), Frac(-12, 5)))
    assert all(isinstance(c, Frac) for c in (*first, *second))
    assert g.distance((5, 0), first) == 4
    assert g.tangent_points((3, 0), (0, 0), 3) == [(3, 0)]  # on the circle: itself
    assert g.tangent_points((1, 0), (0, 0), 3) == []  # inside: none


def test_tangent_points_are_where_the_radius_is_square_to_the_tangent() -> None:
    p, c, r = (4.5, 2.0), (1.0, -1.0), 1.5
    for t in g.tangent_points(p, c, r):
        radius, tangent = (t[0] - c[0], t[1] - c[1]), (p[0] - t[0], p[1] - t[1])
        assert math.hypot(*radius) == pytest.approx(r)
        assert radius[0] * tangent[0] + radius[1] * tangent[1] == pytest.approx(0, abs=1e-12)


def test_lines_cross_exactly_and_parallel_lines_not_at_all() -> None:
    t1, t2 = (Frac(9, 5), Frac(12, 5)), (Frac(9, 5), Frac(-12, 5))
    assert g.line_line(t1, t2, (0, 0), (5, 0)) == (Frac(9, 5), 0)
    assert g.line_line((0, 0), (1, 3), (5, 0), (0, 5)) == (Frac(5, 4), Frac(15, 4))
    assert g.line_line((0, 0), (1, 1), (0, 1), (2, 3)) is None


def test_a_line_meets_a_circle_in_the_order_it_runs() -> None:
    assert g.line_circle((0, 0), (5, 0), (0, 0), 3) == [(-3, 0), (3, 0)]
    assert g.line_circle((5, 0), (0, 0), (0, 0), 3) == [(3, 0), (-3, 0)]
    assert g.line_circle((-5, 3), (5, 3), (0, 0), 3) == [(0, 3)]  # it touches
    assert g.line_circle((-5, 4), (5, 4), (0, 0), 3) == []
    (x, y), _ = g.line_circle((0, 0), (1, 1), (0, 0), 1)
    assert (x, y) == pytest.approx((-math.sqrt(0.5), -math.sqrt(0.5)))


def test_two_circles_meet_left_of_the_way_between_them_first() -> None:
    assert g.circle_circle((0, 0), 5, (8, 0), 5) == [(4, 3), (4, -3)]
    assert g.circle_circle((0, 0), 1, (2, 0), 1) == [(1, 0)]
    assert g.circle_circle((0, 0), 1, (5, 0), 1) == []
    assert g.circle_circle((0, 0), 1, (0, 0), 2) == []
    with pytest.raises(ValueError, match="the same"):
        g.circle_circle((0, 0), 1, (0, 0), 1)


def test_the_foot_of_a_perpendicular_is_exact() -> None:
    # a = (2, 3) onto b = (4, 0): the shadow ends at (2, 0); onto (4, 1) at 11/17 of it
    assert g.foot((2, 3), (0, 0), (4, 0)) == (2, 0)
    assert g.foot((2, 3), (0, 0), (4, 1)) == (Frac(44, 17), Frac(11, 17))
    assert g.midpoint((0, 0), (3, 1)) == (Frac(3, 2), Frac(1, 2))
    assert g.along((5, 0), (Frac(9, 5), Frac(12, 5)), Frac(6, 5)) == (Frac(29, 25), Frac(72, 25))
    assert g.distance((0, 0), (1, 1)) == pytest.approx(math.sqrt(2))


def test_crossings_of_two_functions() -> None:
    found = g.crossings(lambda x: x * x / 4, lambda x: x / 2 + 2, -5, 6)
    assert found == pytest.approx([-2, 4])
    assert g.crossings(math.sin, lambda x: 0.0, 0, 7) == pytest.approx([0, math.pi, 2 * math.pi])
    with pytest.raises(ValueError, match="smaller"):
        g.crossings(math.sin, math.cos, 1, 1)


def test_a_seed_lands_inside_a_shape_whose_centroid_is_outside_it() -> None:
    hook = [(0, 0), (6, 0), (6, 1), (1, 1), (1, 5), (6, 5), (6, 6), (0, 6)]  # a "C"
    assert not Polygon(hook).contains(Polygon(hook).centroid)
    assert Polygon(hook).contains(Point(g.inside_point(hook)))
    with pytest.raises(ValueError, match="no area"):
        g.inside_point([(0, 0), (1, 1), (2, 2)])


def test_through_and_smooth_make_subpaths_through_the_points() -> None:
    assert through([(0, 0), "a.tip", (2, 0)], closed=True) == {
        "start": (0, 0), "segments": [{"line": "a.tip"}, {"line": (2, 0)}], "closed": True,
    }  # fmt: skip
    path = smooth([(0, 0), (1, 1), (2, 0)])
    assert [s["cubic"][2] for s in path["segments"]] == [(1, 1), (2, 0)]
    first, second, _ = path["segments"][0]["cubic"]
    # exact, and level at (1, 1) on both sides, so there is no corner
    assert (first, second) == ((Frac(1, 6), Frac(1, 6)), (Frac(2, 3), Frac(1)))
    closed = smooth([(0, 0), (1, 0), (1, 1)], closed=True)
    assert len(closed["segments"]) == 3 and closed["segments"][-1]["cubic"][2] == (0, 0)
    with pytest.raises(ValueError, match="two"):
        through([(0, 0)])
