"""Geometry a script needs to work out its numbers: intersections, tangents, feet, seed points.

    foot(p, a, b)                         where the perpendicular from p meets line ab
    line_line(a, b, c, d)                 where lines ab and cd cross (None if parallel)
    line_circle(a, b, center, r)          where line ab meets the circle, in order from a to b
    circle_circle(c1, r1, c2, r2)         where two circles meet
    tangent_points(p, center, r)          where the tangents from p touch the circle
    crossings(f, g, lo, hi)               the x where f(x) = g(x), for Python functions
    inside_point(points)                  a point inside a polygon: a seed for flood_fill
    midpoint(p, q), along(p, q, t), distance(p, q)

Points are pairs of numbers (ints, Fractions, floats): these work on what
the script computes, not on references, which only the front-end resolves.
With whole or Fraction inputs the answer stays exact as long as it is
rational: every square root of a perfect square is taken exactly, so the
tangents from (5, 0) to the circle of radius 3 touch it at exactly
(9/5, ±12/5). Anything else is a float. Written into the IR, an exact
answer becomes an expression (``"12/5"``), so it is never rounded on the
way.
"""

import math
from collections.abc import Callable, Sequence
from fractions import Fraction
from typing import Any

from shapely import Polygon

type Num = Any
"""An int, a Fraction or a float."""
type XY = tuple[Num, Num]

BISECTIONS = 60
"""Halvings that pin down a crossing (to 2**-60 of a sample step)."""


def exact(value: Num) -> Num:
    """A whole number as a Fraction, so dividing it stays exact; anything else as it is."""
    return Fraction(value) if isinstance(value, int) and not isinstance(value, bool) else value


def sqrt(value: Num) -> Num:
    """The square root, exact for a perfect square of a Fraction (or int)."""
    value = exact(value)
    if value < 0:
        raise ValueError(f"square root of a negative number ({value})")
    if isinstance(value, Fraction):
        top, bottom = math.isqrt(value.numerator), math.isqrt(value.denominator)
        if top * top == value.numerator and bottom * bottom == value.denominator:
            return Fraction(top, bottom)
    return math.sqrt(value)


def _xy(point: Sequence[Num]) -> XY:
    x, y = point
    return exact(x), exact(y)


def midpoint(p: Sequence[Num], q: Sequence[Num]) -> XY:
    return along(p, q, Fraction(1, 2))


def along(p: Sequence[Num], q: Sequence[Num], t: Num) -> XY:
    """The point ``t`` of the way from ``p`` to ``q`` (beyond q when t > 1)."""
    (px, py), (qx, qy) = _xy(p), _xy(q)
    return px + exact(t) * (qx - px), py + exact(t) * (qy - py)


def distance(p: Sequence[Num], q: Sequence[Num]) -> Num:
    (px, py), (qx, qy) = _xy(p), _xy(q)
    return sqrt((qx - px) ** 2 + (qy - py) ** 2)


def foot(p: Sequence[Num], a: Sequence[Num], b: Sequence[Num]) -> XY:
    """Where the perpendicular from ``p`` meets the line through ``a`` and ``b``."""
    (px, py), (ax, ay), (bx, by) = _xy(p), _xy(a), _xy(b)
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        raise ValueError("a and b are the same point, so they make no line")
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    return ax + t * dx, ay + t * dy


def line_line(a: Sequence[Num], b: Sequence[Num], c: Sequence[Num], d: Sequence[Num]) -> XY | None:
    """Where the line through ``a``, ``b`` crosses the line through ``c``, ``d``; None when
    they are parallel."""
    (ax, ay), (bx, by), (cx, cy), (dx, dy) = _xy(a), _xy(b), _xy(c), _xy(d)
    rx, ry, sx, sy = bx - ax, by - ay, dx - cx, dy - cy
    cross = rx * sy - ry * sx
    if cross == 0:
        return None
    t = ((cx - ax) * sy - (cy - ay) * sx) / cross
    return ax + t * rx, ay + t * ry


def line_circle(a: Sequence[Num], b: Sequence[Num], center: Sequence[Num], r: Num) -> list[XY]:
    """Where the line through ``a`` and ``b`` meets the circle: none, one (it touches) or two,
    in the order the line runs from ``a`` to ``b``."""
    (ax, ay), (bx, by), (cx, cy) = _xy(a), _xy(b), _xy(center)
    dx, dy, fx, fy = bx - ax, by - ay, ax - cx, ay - cy
    k2 = dx * dx + dy * dy
    if k2 == 0:
        raise ValueError("a and b are the same point, so they make no line")
    half_b = fx * dx + fy * dy
    disc = half_b * half_b - k2 * (fx * fx + fy * fy - exact(r) ** 2)
    if disc < 0:
        return []
    root = sqrt(disc)
    ts = [(-half_b - root) / k2] if disc == 0 else [(-half_b - root) / k2, (-half_b + root) / k2]
    return [(ax + t * dx, ay + t * dy) for t in ts]


def circle_circle(c1: Sequence[Num], r1: Num, c2: Sequence[Num], r2: Num) -> list[XY]:
    """Where two circles meet: none, one or two points; the first is on the left of the way
    from ``c1`` to ``c2``. Equal circles (the same center and radius) raise ValueError."""
    (x1, y1), (x2, y2), r1, r2 = _xy(c1), _xy(c2), exact(r1), exact(r2)
    dx, dy = x2 - x1, y2 - y1
    d2 = dx * dx + dy * dy
    if d2 == 0:
        if r1 == r2:
            raise ValueError("the circles are the same, so they meet everywhere")
        return []
    along_ = (d2 + r1 * r1 - r2 * r2) / (2 * d2)  # share of the way from c1 to c2
    h2 = r1 * r1 / d2 - along_ * along_  # (height over the distance) squared
    if h2 < 0:
        return []
    bx, by = x1 + along_ * dx, y1 + along_ * dy
    if h2 == 0:
        return [(bx, by)]
    h = sqrt(h2)
    return [(bx - h * dy, by + h * dx), (bx + h * dy, by - h * dx)]


def tangent_points(p: Sequence[Num], center: Sequence[Num], r: Num) -> list[XY]:
    """Where the tangents from ``p`` touch the circle: two points, the first counterclockwise
    from ``p`` around the center; one when ``p`` is on the circle, none inside it."""
    (px, py), (cx, cy), r = _xy(p), _xy(center), exact(r)
    dx, dy = px - cx, py - cy
    d2 = dx * dx + dy * dy
    if d2 < r * r:
        return []
    if d2 == r * r:
        return [(px, py)]
    near = r * r / d2  # the touching points' foot on the line to p, as a share of it
    side = r * sqrt(d2 - r * r) / d2
    return [
        (cx + near * dx - side * dy, cy + near * dy + side * dx),
        (cx + near * dx + side * dy, cy + near * dy - side * dx),
    ]


def crossings(
    f: Callable[[float], float],
    g: Callable[[float], float],
    lo: float,
    hi: float,
    samples: int = 400,
) -> list[float]:
    """The x between ``lo`` and ``hi`` where ``f(x) = g(x)``, found where f - g changes sign
    from one of ``samples`` even steps to the next (a crossing inside one step and back is
    missed: give more samples)."""
    if not lo < hi:
        raise ValueError(f"lo ({lo:g}) must be smaller than hi ({hi:g})")
    xs = [lo + (hi - lo) * k / samples for k in range(samples + 1)]
    gap = [float(f(x)) - float(g(x)) for x in xs]
    found: list[float] = []
    for k in range(samples):
        (x0, h0), (x1, h1) = (xs[k], gap[k]), (xs[k + 1], gap[k + 1])
        if h0 == 0:
            found.append(x0)
        elif h0 * h1 < 0:
            for _ in range(BISECTIONS):
                mid = (x0 + x1) / 2
                h = float(f(mid)) - float(g(mid))
                if h == 0:
                    break
                if (h < 0) == (h0 < 0):
                    x0, h0 = mid, h
                else:
                    x1 = mid
            found.append((x0 + x1) / 2)
    if gap[-1] == 0:
        found.append(xs[-1])
    return found


def inside_point(points: Sequence[Sequence[Num]]) -> tuple[float, float]:
    """A point inside the polygon through ``points``, never on its outline: a seed for a
    flood_fill whose boundaries trace that polygon. The centroid is not one: it can fall
    outside a bent shape."""
    shape = Polygon([(float(x), float(y)) for x, y in points])
    if not shape.is_valid:  # an outline that crosses itself: the area it encloses
        shape = shape.buffer(0)
    if shape.is_empty or shape.area == 0:
        raise ValueError("the points enclose no area")
    seed = shape.representative_point()
    return seed.x, seed.y
