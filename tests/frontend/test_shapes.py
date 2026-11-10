"""Every shape as LIR geometry, and group transforms as matrices."""

import math
from typing import Any

import pytest
from pydantic import TypeAdapter

from irpipe.frontend import shapes
from irpipe.frontend.geometry.affine import Matrix
from irpipe.schema import lir
from irpipe.schema.ir import Group, Shape

SHAPE: TypeAdapter[Shape] = TypeAdapter(Shape)


def ends(subpath: lir.Subpath) -> list[tuple[float, float]]:
    """The start point and the end point of every segment."""
    points = [subpath.start]
    for segment in subpath.segments:
        if isinstance(segment, lir.LineTo):
            points.append(segment.line)
        elif isinstance(segment, lir.CubicTo):
            points.append(segment.cubic[-1])
        else:
            points.append(segment.quad[-1])
    return points


def near(points: list[tuple[float, float]]) -> list[Any]:
    return [pytest.approx(point, abs=1e-9) for point in points]


def bezier_midpoint(start: tuple[float, float], cubic: lir.CubicTo) -> tuple[float, float]:
    (x1, y1), (x2, y2), (x3, y3) = cubic.cubic
    x0, y0 = start
    return (x0 + 3 * x1 + 3 * x2 + x3) / 8, (y0 + 3 * y1 + 3 * y2 + y3) / 8


# Closed shapes


def test_an_ellipse_passes_through_its_four_extremes() -> None:
    subpath = shapes.ellipse((1, 2), 2, 0.5)
    assert ends(subpath) == near([(3, 2), (1, 2.5), (-1, 2), (1, 1.5), (3, 2)])
    assert subpath.closed


def test_a_bezier_quarter_circle_stays_on_the_circle() -> None:
    subpath = shapes.ellipse((0, 0), 1, 1)
    first = subpath.segments[0]
    assert isinstance(first, lir.CubicTo)
    x, y = bezier_midpoint(subpath.start, first)  # where the approximation is worst
    assert math.hypot(x, y) == pytest.approx(1, abs=3e-4)


def test_a_sharp_rectangle_visits_its_corners() -> None:
    assert ends(shapes.rect((0, 0), 4, 2, 0)) == [(-2, -1), (2, -1), (2, 1), (-2, 1)]


def test_a_corner_radius_is_clamped_to_half_the_short_side() -> None:
    assert ends(shapes.rect((0, 0), 4, 2, 5))[0] == pytest.approx((-1, -1))  # r became 1


@pytest.mark.parametrize(
    ("sides", "corners"),
    [
        (3, [(math.sqrt(3) / 2, -0.5), (0, 1), (-math.sqrt(3) / 2, -0.5)]),  # point up
        (4, [(1, -1), (1, 1), (-1, 1), (-1, -1)]),  # axis-aligned square
    ],
)
def test_a_regular_polygon_stands_on_a_flat_bottom_edge(
    sides: int, corners: list[tuple[float, float]]
) -> None:
    radius = 1 if sides == 3 else math.sqrt(2)
    points = shapes.regular_polygon_points((0, 0), radius, sides, 0)
    assert points == near(corners)


def test_every_corner_of_a_regular_polygon_is_on_its_circle() -> None:
    for x, y in shapes.regular_polygon_points((1, 1), 2, 7, 13):
        assert math.hypot(x - 1, y - 1) == pytest.approx(2)


def test_rotation_turns_a_regular_polygon_counterclockwise() -> None:
    upright = shapes.regular_polygon_points((0, 0), 1, 3, 0)
    turned = shapes.regular_polygon_points((0, 0), 1, 3, 90)
    assert turned[1] == pytest.approx((-1, 0))  # the top corner moved to the left
    assert upright[1] == pytest.approx((0, 1))


def test_a_sector_runs_from_the_center_round_the_arc_and_back() -> None:
    subpath = shapes.sector((0, 0), 2, 0, 90)
    assert subpath.start == (0, 0)
    assert ends(subpath) == near([(0, 0), (2, 0), (0, 2)])
    assert subpath.closed


# Open shapes


@pytest.mark.parametrize(
    ("start", "end", "pieces", "last"),
    [
        (0, 90, 1, (0, 1)),
        (0, 270, 3, (0, -1)),
        (0, 360, 4, (1, 0)),
        (90, 0, 1, (1, 0)),  # clockwise
        (0, 100, 2, (math.cos(math.radians(100)), math.sin(math.radians(100)))),
    ],
)
def test_an_arc_is_cut_into_pieces_of_at_most_90_degrees(
    start: float, end: float, pieces: int, last: tuple[float, float]
) -> None:
    subpath = shapes.arc((0, 0), 1, start, end)
    assert len(subpath.segments) == pieces
    assert ends(subpath)[-1] == pytest.approx(last)
    assert not subpath.closed


def test_a_clockwise_arc_bends_the_short_way() -> None:
    subpath = shapes.arc((0, 0), 1, 90, 0)
    first = subpath.segments[0]
    assert isinstance(first, lir.CubicTo)
    x, y = bezier_midpoint(subpath.start, first)
    assert (x, y) == pytest.approx((math.sqrt(0.5), math.sqrt(0.5)), abs=3e-4)


def test_a_polyline_goes_through_its_points_and_stays_open() -> None:
    subpath = shapes.polyline([(0, 0), (1, 1), (2, 0)])
    assert ends(subpath) == [(0, 0), (1, 1), (2, 0)]
    assert not subpath.closed


# outline(): one door for every shape


SHAPES: list[tuple[dict[str, Any], str | None, bool]] = [
    ({"type": "circle", "center": [0, 0], "radius": 1}, "circle", True),
    ({"type": "ellipse", "center": [0, 0], "rx": 2, "ry": 1}, "ellipse", True),
    ({"type": "rect", "center": [0, 0], "width": 2, "height": 1}, "rect", True),
    (
        {"type": "regular_polygon", "center": [0, 0], "radius": 1, "sides": 5},
        "regular_polygon",
        True,
    ),
    ({"type": "polygon", "points": [[0, 0], [1, 0], [0, 1]]}, "polygon", True),
    (
        {"type": "sector", "center": [0, 0], "radius": 1, "start_angle": 0, "end_angle": 45},
        "sector",
        True,
    ),
    ({"type": "line", "start": [0, 0], "end": [1, 1]}, "line", False),
    ({"type": "polyline", "points": [[0, 0], [1, 1], [2, 0]]}, "polyline", False),
    (
        {"type": "arc", "center": [0, 0], "radius": 1, "start_angle": 0, "end_angle": 45},
        "arc",
        False,
    ),
    (
        {"type": "path", "subpaths": [{"start": [0, 0], "segments": [{"line": [1, 0]}]}]},
        None,
        False,
    ),
]


@pytest.mark.parametrize(("data", "hint", "closed"), SHAPES)
def test_every_shape_has_an_outline_and_keeps_its_name_as_the_hint(
    data: dict[str, Any], hint: str | None, closed: bool
) -> None:
    subpaths, found, rule = shapes.outline(SHAPE.validate_python({"id": "s", **data}))
    assert (found.shape if found else None) == hint
    assert subpaths[0].closed is closed
    assert rule == "nonzero"


def test_the_hint_carries_the_shapes_own_numbers() -> None:
    arc = SHAPE.validate_python(
        {
            "id": "s",
            "type": "arc",
            "center": [1, 2],
            "radius": 3,
            "start_angle": 10,
            "end_angle": 80,
        }
    )
    _, hint, _ = shapes.outline(arc)
    assert hint == lir.ArcHint(center=(1, 2), radius=3, start_angle=10, end_angle=80)


# Group transforms


def group(**fields: object) -> Group:
    return Group.model_validate({"id": "g", "type": "group", "children": ["a"], **fields})


def apply(matrix: Matrix, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = matrix
    return a * x + c * y + e, b * x + d * y + f


def test_no_transform_is_the_identity() -> None:
    assert shapes.group_matrix(group()) == (1, 0, 0, 1, 0, 0)


def test_rotation_turns_counterclockwise_about_the_pivot() -> None:
    m = shapes.group_matrix(group(rotate=90, pivot=[1, 1]))
    assert apply(m, 1, 1) == pytest.approx((1, 1))  # the pivot stays
    assert apply(m, 2, 1) == pytest.approx((1, 2))  # a point to its right moves above it


def test_scale_then_rotate_then_translate() -> None:
    m = shapes.group_matrix(group(scale=[2, 1], rotate=90, translate=[10, 0]))
    assert apply(m, 1, 0) == pytest.approx((10, 2))
