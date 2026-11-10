"""Measuring and cutting LIR subpaths: lengths, points along them, bounds, trimming.

A subpath is cut into pieces, each a tuple of its control points: two for a
straight segment, three for a quadratic, four for a cubic Bezier (a closed
subpath's closing edge is one more straight piece). Lengths are measured on
each piece cut into ``SAMPLES`` straight bits, which is far closer than a
pixel for the curves the front-end makes; bounds are exact.

Positions along a path are by length: ``t`` = 0.5 is halfway along it, not
halfway through its segments. Moving from one subpath to the next adds no
length.
"""

import math
from collections.abc import Sequence
from itertools import pairwise

from irpipe.frontend.geometry.affine import XY, Box, Matrix, apply, bounds
from irpipe.schema import lir

SAMPLES = 64
"""Straight bits per piece when measuring a curve's length."""

type Piece = tuple[XY, ...]


def pieces(subpath: lir.Subpath) -> list[Piece]:
    """Every segment of ``subpath`` with its start point, plus the closing edge if any."""
    out: list[Piece] = []
    current = subpath.start
    for segment in subpath.segments:
        match segment:
            case lir.LineTo(line=p):
                out.append((current, p))
            case lir.QuadTo(quad=(c, p)):
                out.append((current, c, p))
            case lir.CubicTo(cubic=(c1, c2, p)):
                out.append((current, c1, c2, p))
        current = out[-1][-1]
    if subpath.closed and current != subpath.start:
        out.append((current, subpath.start))
    return out


def subpath_of(parts: Sequence[Piece], *, closed: bool = False) -> lir.Subpath:
    """The pieces back as a subpath (they must follow each other)."""
    segments: list[lir.Segment] = []
    for piece in parts:
        if len(piece) == 2:
            segments.append(lir.LineTo(line=piece[1]))
        elif len(piece) == 3:
            segments.append(lir.QuadTo(quad=(piece[1], piece[2])))
        else:
            segments.append(lir.CubicTo(cubic=(piece[1], piece[2], piece[3])))
    return lir.Subpath(start=parts[0][0], segments=tuple(segments), closed=closed)


def point(piece: Piece, t: float) -> XY:
    """The point at parameter ``t`` (de Casteljau)."""
    level = list(piece)
    while len(level) > 1:
        level = [_mix(p, q, t) for p, q in pairwise(level)]
    return level[0]


def derivative(piece: Piece, t: float) -> XY:
    """The direction of travel at ``t`` (not normalized)."""
    n = len(piece) - 1
    hull = [(n * (q[0] - p[0]), n * (q[1] - p[1])) for p, q in pairwise(piece)]
    return point(tuple(hull), t) if len(hull) > 1 else hull[0]


def split(piece: Piece, t: float) -> tuple[Piece, Piece]:
    """The piece cut at ``t`` into the part before and the part after."""
    left, right, level = [piece[0]], [piece[-1]], list(piece)
    while len(level) > 1:
        level = [_mix(p, q, t) for p, q in pairwise(level)]
        left.append(level[0])
        right.append(level[-1])
    return tuple(left), tuple(reversed(right))


def length(piece: Piece) -> float:
    return _cumulative(piece)[-1]


def subpaths_length(subpaths: Sequence[lir.Subpath]) -> float:
    return sum(length(piece) for s in subpaths for piece in pieces(s))


def point_at(subpaths: Sequence[lir.Subpath], t: float) -> tuple[XY, XY]:
    """The point ``t`` of the way along the subpaths by length, and the unit direction there."""
    parts = [piece for s in subpaths for piece in pieces(s)]
    lengths = [length(piece) for piece in parts]
    goal = t * sum(lengths)
    for piece, piece_length in zip(parts, lengths, strict=True):
        if goal <= piece_length or piece is parts[-1]:
            u = _parameter_at(piece, min(goal, piece_length))
            return point(piece, u), _unit(_direction(piece, u))
        goal -= piece_length
    raise ValueError("no subpaths")


def crossing(subpaths: Sequence[lir.Subpath], x: float) -> XY | None:
    """The first point, in drawing order, where the subpaths reach ``x``; None if they never do."""
    for s in subpaths:
        for piece in pieces(s):
            samples = [point(piece, k / SAMPLES) for k in range(SAMPLES + 1)]
            for p, q in pairwise(samples):
                if min(p[0], q[0]) <= x <= max(p[0], q[0]):
                    if p[0] == q[0]:
                        return p
                    share = (x - p[0]) / (q[0] - p[0])
                    return (x, p[1] + share * (q[1] - p[1]))
    return None


def start_direction(subpaths: Sequence[lir.Subpath]) -> XY:
    """The unit direction the subpaths set off in."""
    first = pieces(subpaths[0])[0]
    return _unit(_direction(first, 0.0))


def end_direction(subpaths: Sequence[lir.Subpath]) -> XY:
    """The unit direction the subpaths arrive in."""
    last = pieces(subpaths[-1])[-1]
    return _unit(_direction(last, 1.0))


def end_point(subpaths: Sequence[lir.Subpath]) -> XY:
    return pieces(subpaths[-1])[-1][-1]


def bbox(subpaths: Sequence[lir.Subpath]) -> Box:
    """The exact box around the subpaths' curves (control points outside it do not count)."""
    found: list[XY] = []
    for s in subpaths:
        for piece in pieces(s):
            found.extend((piece[0], piece[-1]))
            for t in _extrema(piece):
                found.append(point(piece, t))
    return bounds(found)


def transform(subpaths: Sequence[lir.Subpath], m: Matrix) -> tuple[lir.Subpath, ...]:
    """The subpaths through an affine map (exact: a map of a Bezier is a Bezier)."""
    return tuple(
        subpath_of([tuple(apply(m, p) for p in piece) for piece in pieces(s)], closed=s.closed)
        for s in subpaths
    )


def trim(subpaths: Sequence[lir.Subpath], start: float, end: float) -> tuple[lir.Subpath, ...]:
    """The subpaths with ``start`` cut off the first one's start and ``end`` off the last one's end.

    Lengths are in the subpaths' units. A closed subpath is not cut. Cuts
    longer than nine tenths of a subpath are shortened in proportion, so
    something of the line is always left.
    """
    out = list(subpaths)
    if start > 0 and not out[0].closed:
        out[0] = _cut_start(out[0], start, _room(out[0], start, end if len(out) == 1 else 0))
    if end > 0 and not out[-1].closed:
        reversed_last = _reverse(out[-1])
        room = _room(out[-1], end, start if len(out) == 1 else 0)
        out[-1] = _reverse(_cut_start(reversed_last, end, room))
    return tuple(out)


def _room(subpath: lir.Subpath, cut: float, other: float) -> float:
    total = sum(length(piece) for piece in pieces(subpath))
    if cut + other <= 0.9 * total:
        return 1.0
    return 0.9 * total / (cut + other)


def _cut_start(subpath: lir.Subpath, cut: float, room: float) -> lir.Subpath:
    goal = cut * room
    parts = pieces(subpath)
    for k, piece in enumerate(parts):
        piece_length = length(piece)
        if goal < piece_length:
            _, after = split(piece, _parameter_at(piece, goal))
            return subpath_of([after, *parts[k + 1 :]])
        goal -= piece_length
    return subpath


def _reverse(subpath: lir.Subpath) -> lir.Subpath:
    parts = [tuple(reversed(piece)) for piece in reversed(pieces(subpath))]
    return subpath_of(parts)


def _parameter_at(piece: Piece, distance: float) -> float:
    """The parameter at which ``distance`` of the piece's length lies behind."""
    cumulative = _cumulative(piece)
    for k in range(1, len(cumulative)):
        if cumulative[k] >= distance:
            step = cumulative[k] - cumulative[k - 1]
            share = 0.0 if step == 0 else (distance - cumulative[k - 1]) / step
            return (k - 1 + share) / SAMPLES
    return 1.0


def _cumulative(piece: Piece) -> list[float]:
    """The length covered at each of the piece's ``SAMPLES`` + 1 evenly spaced parameters."""
    if len(piece) == 2:
        full = math.dist(piece[0], piece[1])
        return [full * k / SAMPLES for k in range(SAMPLES + 1)]
    samples = [point(piece, k / SAMPLES) for k in range(SAMPLES + 1)]
    total, out = 0.0, [0.0]
    for p, q in pairwise(samples):
        total += math.dist(p, q)
        out.append(total)
    return out


def _direction(piece: Piece, t: float) -> XY:
    """The way the piece runs at ``t``.

    Where a control point sits on the end point the derivative vanishes;
    the way from (or toward) the nearest other control point is taken.
    """
    d = derivative(piece, t)
    if d != (0.0, 0.0):
        return d
    here = point(piece, t)
    others = [p for p in piece if p != here]
    if not others:
        return (1.0, 0.0)
    if t < 1:
        q = others[0]
        return (q[0] - here[0], q[1] - here[1])
    q = others[-1]
    return (here[0] - q[0], here[1] - q[1])


def _extrema(piece: Piece) -> list[float]:
    """Parameters in (0, 1) where the piece turns in x or in y."""
    if len(piece) == 2:
        return []
    found = []
    for axis in (0, 1):
        values = [p[axis] for p in piece]
        if len(values) == 3:
            a, b, c = values
            denominator = a - 2 * b + c
            if denominator != 0:
                found.append((a - b) / denominator)
        else:
            a, b, c, d = values
            # derivative / 3: (b-a)(1-t)^2 + 2(c-b)(1-t)t + (d-c)t^2 = qa t^2 + qb t + qc
            qa = (b - a) - 2 * (c - b) + (d - c)
            qb = 2 * ((c - b) - (b - a))
            qc = b - a
            found.extend(_roots(qa, qb, qc))
    return [t for t in found if 0 < t < 1]


def _roots(a: float, b: float, c: float) -> list[float]:
    if abs(a) < 1e-12:
        return [] if abs(b) < 1e-12 else [-c / b]
    disc = b * b - 4 * a * c
    if disc < 0:
        return []
    root = math.sqrt(disc)
    return [(-b + root) / (2 * a), (-b - root) / (2 * a)]


def _mix(p: XY, q: XY, t: float) -> XY:
    return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)


def _unit(v: XY) -> XY:
    norm = math.hypot(*v)
    return (1.0, 0.0) if norm == 0 else (v[0] / norm, v[1] / norm)
