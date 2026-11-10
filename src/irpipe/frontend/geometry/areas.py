"""Areas and lines as shapely geometry, and back to LIR subpaths.

The set operations of regions, flood fills and clips run on shapely (GEOS),
which works on straight segments: curves are cut into short straight bits
on the way in (curves.SAMPLES per quarter circle, far finer than a pixel).
What comes back is straight subpaths, with holes as extra subpaths drawn
with the even-odd rule.

An area follows its subpaths' fill rule, as SVG does. The subpaths' lines
cut the plane into faces; a face is inside when an odd number of subpaths
go round it (even-odd), or when the subpaths going round it counterclockwise
and clockwise do not cancel out (nonzero).
"""

from collections.abc import Iterator, Sequence
from itertools import pairwise
from typing import Final, Literal

import shapely
from shapely import affinity
from shapely.geometry import LineString, MultiLineString, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient
from shapely.ops import polygonize

from irpipe.frontend.geometry.affine import XY, Box, Matrix
from irpipe.frontend.geometry.curves import flatten, subpath_of
from irpipe.schema import lir

type FillRule = Literal["nonzero", "evenodd"]

EMPTY: Final[BaseGeometry] = Polygon()


def area(subpaths: Sequence[lir.Subpath], rule: FillRule = "nonzero") -> BaseGeometry:
    """The inside of the subpaths, each closed as a fill closes it."""
    rings = [points for s in subpaths if len(points := _closed(flatten(s))) >= 4]
    if not rings:
        return EMPTY
    if len(rings) == 1:
        return _valid(Polygon(rings[0]))
    surrounds = [(Polygon(points), 1 if _signed_area(points) > 0 else -1) for points in rings]
    faces = polygonize(list(_parts(shapely.union_all([LineString(points) for points in rings]))))
    inside = []
    for face in faces:
        probe = face.representative_point()
        around = [turn for polygon, turn in surrounds if polygon.contains(probe)]
        if (len(around) % 2 == 1) if rule == "evenodd" else (sum(around) != 0):
            inside.append(face)
    return shapely.union_all(inside) if inside else EMPTY


def lines(subpaths: Sequence[lir.Subpath]) -> BaseGeometry:
    """The subpaths as lines (a closed subpath as a closed line)."""
    found = [LineString(points) for s in subpaths if len(points := flatten(s)) >= 2]
    return MultiLineString(found) if found else EMPTY


def subpaths(geometry: BaseGeometry) -> tuple[lir.Subpath, ...]:
    """Polygons as closed subpaths (each hole one more), lines as open ones."""
    out: list[lir.Subpath] = []
    for part in _parts(geometry):
        if isinstance(part, Polygon):
            polygon = orient(part)  # outer rings counterclockwise, holes clockwise
            for ring in (polygon.exterior, *polygon.interiors):
                out.append(_polyline(list(ring.coords)[:-1], closed=True))
        elif isinstance(part, LineString) and len(part.coords) >= 2:
            points = list(part.coords)
            if points[0] == points[-1] and len(points) > 3:
                out.append(_polyline(points[:-1], closed=True))
            else:
                out.append(_polyline(points, closed=False))
    return tuple(out)


def transform(geometry: BaseGeometry, m: Matrix) -> BaseGeometry:
    """The geometry through an affine map ``(a, b, c, d, e, f)``."""
    a, b, c, d, e, f = m
    return affinity.affine_transform(geometry, [a, c, b, d, e, f])


def half_plane(p: XY, q: XY, around: Box) -> BaseGeometry:
    """The part of the plane left of the line from ``p`` to ``q``, as far as ``around`` reaches.

    The plane is endless; a polygon reaching well past ``around`` (the frame)
    stands in for it.
    """
    (px, py), (qx, qy) = p, q
    length = ((qx - px) ** 2 + (qy - py) ** 2) ** 0.5
    if length == 0:
        raise ValueError("a half plane needs two different points")
    x0, y0, x1, y1 = around
    far = 10 * (abs(x0) + abs(x1) + abs(y0) + abs(y1) + length)
    ux, uy = (qx - px) / length, (qy - py) / length
    left = (-uy, ux)
    back = (px - ux * far, py - uy * far)
    ahead = (px + ux * far, py + uy * far)
    return Polygon(
        [
            back,
            ahead,
            (ahead[0] + left[0] * far, ahead[1] + left[1] * far),
            (back[0] + left[0] * far, back[1] + left[1] * far),
        ]
    )


def under(graph: Sequence[XY]) -> BaseGeometry:
    """Between a graph (its points, left to right) and the line y = 0."""
    (x0, _), (x1, _) = graph[0], graph[-1]
    return _valid(Polygon([(x0, 0.0), *graph, (x1, 0.0)]))


def between(upper: Sequence[XY], lower: Sequence[XY]) -> BaseGeometry:
    """Between two graphs given left to right."""
    return _valid(Polygon([*upper, *reversed(lower)]))


def is_empty(geometry: BaseGeometry) -> bool:
    return bool(geometry.is_empty) or geometry.area <= 1e-12


def _closed(points: list[XY]) -> list[XY]:
    return points if points[0] == points[-1] else [*points, points[0]]


def _valid(polygon: Polygon) -> BaseGeometry:
    """A polygon whose outline crosses itself becomes the areas it encloses."""
    if polygon.is_valid:
        return polygon
    return shapely.make_valid(polygon).buffer(0)


def _signed_area(points: list[XY]) -> float:
    return (
        sum(
            p[0] * q[1] - q[0] * p[1] for p, q in zip(points, [*points[1:], points[0]], strict=True)
        )
        / 2
    )


def _parts(geometry: BaseGeometry) -> Iterator[BaseGeometry]:
    if geometry.is_empty:
        return
    if hasattr(geometry, "geoms"):
        for part in geometry.geoms:
            yield from _parts(part)
    else:
        yield geometry


def _polyline(points: list[tuple[float, ...]], *, closed: bool) -> lir.Subpath:
    corners = [(float(p[0]), float(p[1])) for p in points]
    return subpath_of(list(pairwise(corners)), closed=closed)
