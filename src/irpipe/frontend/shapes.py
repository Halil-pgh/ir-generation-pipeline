"""Every IR shape as LIR geometry, and a group's transform as a matrix.

    subpaths, hint, rule = outline(shape)

Backends only ever draw paths, so this is the one place that knows what a
circle or a sector is. Curves become cubic Bezier pieces of at most 90
degrees each (the standard approximation, off by less than 0.03% of the
radius). Each shape keeps its name and numbers as a hint, so a backend may
still use its own class for it.
"""

import math
from collections.abc import Sequence
from typing import Literal

from irpipe.schema import lir
from irpipe.schema.ir import (
    Arc,
    Circle,
    Ellipse,
    Group,
    Line,
    Path,
    Point,
    Polygon,
    Polyline,
    Rect,
    RegularPolygon,
    Sector,
    Shape,
)

KAPPA = 4 * (math.sqrt(2) - 1) / 3
"""Control-point distance, as a share of the radius, for a quarter circle as one cubic."""

type Matrix = tuple[float, float, float, float, float, float]
type FillRule = Literal["nonzero", "evenodd"]
type Outline = tuple[tuple[lir.Subpath, ...], lir.ShapeHint | None, FillRule]


def outline(shape: Shape) -> Outline:
    """The subpaths, the hint and the fill rule of any IR shape."""
    hint: lir.ShapeHint
    match shape:
        case Circle(center=c, radius=r):
            return (ellipse(c, r, r),), lir.CircleHint(center=c, radius=r), "nonzero"
        case Ellipse(center=c, rx=rx, ry=ry):
            return (ellipse(c, rx, ry),), lir.EllipseHint(center=c, rx=rx, ry=ry), "nonzero"
        case Rect(center=c, width=w, height=h, corner_radius=r):
            hint = lir.RectHint(center=c, width=w, height=h, corner_radius=r)
            return (rect(c, w, h, r),), hint, "nonzero"
        case RegularPolygon(center=c, radius=r, sides=n, rotation=turn):
            hint = lir.RegularPolygonHint(center=c, radius=r, sides=n, rotation=turn)
            return (polyline(regular_polygon_points(c, r, n, turn), closed=True),), hint, "nonzero"
        case Polygon(points=points):
            hint = lir.PolygonHint(points=points)
            return (polyline(points, closed=True),), hint, "nonzero"
        case Sector(center=c, radius=r, start_angle=a, end_angle=b):
            hint = lir.SectorHint(center=c, radius=r, start_angle=a, end_angle=b)
            return (sector(c, r, a, b),), hint, "nonzero"
        case Line(start=p, end=q):
            return (polyline((p, q)),), lir.LineHint(start=p, end=q), "nonzero"
        case Polyline(points=points):
            return (polyline(points),), lir.PolylineHint(points=points), "nonzero"
        case Arc(center=c, radius=r, start_angle=a, end_angle=b):
            hint = lir.ArcHint(center=c, radius=r, start_angle=a, end_angle=b)
            return (arc(c, r, a, b),), hint, "nonzero"
        case Path(subpaths=subpaths, fill_rule=rule):
            return tuple(lir.Subpath.model_validate(s.model_dump()) for s in subpaths), None, rule
    raise TypeError(f"no outline for {type(shape).__name__}")


def ellipse(center: Point, rx: float, ry: float) -> lir.Subpath:
    """A closed ellipse of four quarter arcs, starting at its rightmost point."""
    cx, cy = center
    kx, ky = KAPPA * rx, KAPPA * ry
    quarters = [
        ((cx + rx, cy + ky), (cx + kx, cy + ry), (cx, cy + ry)),
        ((cx - kx, cy + ry), (cx - rx, cy + ky), (cx - rx, cy)),
        ((cx - rx, cy - ky), (cx - kx, cy - ry), (cx, cy - ry)),
        ((cx + kx, cy - ry), (cx + rx, cy - ky), (cx + rx, cy)),
    ]
    return lir.Subpath(
        start=(cx + rx, cy), segments=tuple(lir.CubicTo(cubic=q) for q in quarters), closed=True
    )


def rect(center: Point, width: float, height: float, corner_radius: float) -> lir.Subpath:
    """A rectangle drawn counterclockwise from the bottom edge; corners clamp to half a side."""
    cx, cy = center
    x0, x1, y0, y1 = cx - width / 2, cx + width / 2, cy - height / 2, cy + height / 2
    r = min(corner_radius, width / 2, height / 2)
    if r <= 0:
        return polyline(((x0, y0), (x1, y0), (x1, y1), (x0, y1)), closed=True)
    k = KAPPA * r
    segments: list[lir.Segment] = [
        lir.LineTo(line=(x1 - r, y0)),
        lir.CubicTo(cubic=((x1 - r + k, y0), (x1, y0 + r - k), (x1, y0 + r))),
        lir.LineTo(line=(x1, y1 - r)),
        lir.CubicTo(cubic=((x1, y1 - r + k), (x1 - r + k, y1), (x1 - r, y1))),
        lir.LineTo(line=(x0 + r, y1)),
        lir.CubicTo(cubic=((x0 + r - k, y1), (x0, y1 - r + k), (x0, y1 - r))),
        lir.LineTo(line=(x0, y0 + r)),
        lir.CubicTo(cubic=((x0, y0 + r - k), (x0 + r - k, y0), (x0 + r, y0))),
    ]
    return lir.Subpath(start=(x0 + r, y0), segments=tuple(segments), closed=True)


def polyline(points: Sequence[Point], *, closed: bool = False) -> lir.Subpath:
    """Straight segments through ``points``; ``closed`` joins the last point to the first."""
    return lir.Subpath(
        start=points[0], segments=tuple(lir.LineTo(line=p) for p in points[1:]), closed=closed
    )


def regular_polygon_points(
    center: Point, radius: float, sides: int, rotation: float
) -> list[Point]:
    """Corners counterclockwise; at rotation 0 the bottom edge is horizontal."""
    cx, cy = center
    first = -90 + 180 / sides + rotation
    angles = [math.radians(first + k * 360 / sides) for k in range(sides)]
    return [(cx + radius * math.cos(a), cy + radius * math.sin(a)) for a in angles]


def arc_segments(center: Point, radius: float, start: float, end: float) -> list[lir.CubicTo]:
    """Cubic pieces of at most 90 degrees from angle ``start`` to ``end`` (degrees)."""
    cx, cy = center
    pieces = max(1, math.ceil(abs(end - start) / 90 - 1e-9))
    step = math.radians(end - start) / pieces
    reach = 4 / 3 * math.tan(step / 4) * radius  # control distance; negative turns clockwise
    segments = []
    for k in range(pieces):
        a = math.radians(start) + k * step
        b = a + step
        p0 = (cx + radius * math.cos(a), cy + radius * math.sin(a))
        p3 = (cx + radius * math.cos(b), cy + radius * math.sin(b))
        c1 = (p0[0] - reach * math.sin(a), p0[1] + reach * math.cos(a))
        c2 = (p3[0] + reach * math.sin(b), p3[1] - reach * math.cos(b))
        segments.append(lir.CubicTo(cubic=(c1, c2, p3)))
    return segments


def arc(center: Point, radius: float, start: float, end: float) -> lir.Subpath:
    cx, cy = center
    first = (
        cx + radius * math.cos(math.radians(start)),
        cy + radius * math.sin(math.radians(start)),
    )
    return lir.Subpath(start=first, segments=tuple(arc_segments(center, radius, start, end)))


def sector(center: Point, radius: float, start: float, end: float) -> lir.Subpath:
    """From the center out along the first radius, round the arc, and back."""
    cx, cy = center
    first = (
        cx + radius * math.cos(math.radians(start)),
        cy + radius * math.sin(math.radians(start)),
    )
    segments: list[lir.Segment] = [lir.LineTo(line=first)]
    segments.extend(arc_segments(center, radius, start, end))
    return lir.Subpath(start=center, segments=tuple(segments), closed=True)


def group_matrix(group: Group) -> Matrix:
    """Scale, then rotate (degrees, counterclockwise) about the pivot, then translate."""
    sx, sy = group.scale if isinstance(group.scale, tuple) else (group.scale, group.scale)
    turn = math.radians(group.rotate)
    cos, sin = math.cos(turn), math.sin(turn)
    a, b, c, d = cos * sx, sin * sx, -sin * sy, cos * sy
    (px, py), (tx, ty) = group.pivot, group.translate
    e = px + tx - (a * px + c * py)
    f = py + ty - (b * px + d * py)
    return (a, b, c, d, e, f)
