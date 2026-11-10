"""2D affine maps as ``(a, b, c, d, e, f)``: (x, y) goes to (a x + c y + e, b x + d y + f).

This is the LIR's and SVG's matrix order. ``compose(outer, inner)`` applies
``inner`` first.
"""

from collections.abc import Iterable
from typing import Final

type Matrix = tuple[float, float, float, float, float, float]
type XY = tuple[float, float]
type Box = tuple[float, float, float, float]

IDENTITY: Final[Matrix] = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def translation(dx: float, dy: float) -> Matrix:
    return (1.0, 0.0, 0.0, 1.0, dx, dy)


def scaling(sx: float, sy: float) -> Matrix:
    return (sx, 0.0, 0.0, sy, 0.0, 0.0)


def compose(outer: Matrix, inner: Matrix) -> Matrix:
    """The map that applies ``inner``, then ``outer``."""
    a1, b1, c1, d1, e1, f1 = outer
    a2, b2, c2, d2, e2, f2 = inner
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def invert(m: Matrix) -> Matrix:
    a, b, c, d, e, f = m
    det = a * d - b * c
    if det == 0:
        raise ValueError("the map flattens the plane and cannot be inverted")
    ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
    return (ia, ib, ic, id_, -(ia * e + ic * f), -(ib * e + id_ * f))


def apply(m: Matrix, point: XY) -> XY:
    a, b, c, d, e, f = m
    x, y = point
    return (a * x + c * y + e, b * x + d * y + f)


def apply_linear(m: Matrix, vector: XY) -> XY:
    """``m`` without its translation: for directions and shifts."""
    a, b, c, d, _, _ = m
    x, y = vector
    return (a * x + c * y, b * x + d * y)


def bounds(points: Iterable[XY]) -> Box:
    xs, ys = zip(*points, strict=True)
    return (min(xs), min(ys), max(xs), max(ys))


def transform_box(m: Matrix, box: Box) -> Box:
    """The axis-aligned box around ``box`` after ``m`` (larger than the box if ``m`` turns)."""
    x0, y0, x1, y1 = box
    return bounds(apply(m, p) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)))


def union(boxes: Iterable[Box]) -> Box:
    x0s, y0s, x1s, y1s = zip(*boxes, strict=True)
    return (min(x0s), min(y0s), max(x1s), max(y1s))
