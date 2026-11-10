"""Lowering: the LIR rewritten with only what the chosen backend can draw (analysis §3).

    lowered, problems = lower(lir, backend.capabilities)

The front-end's LIR is the same for every backend (lir.json). Just before a
backend draws it, every feature the backend does not list is rewritten
with simpler ones:

    cubic curves      -> quadratic curves (within ``TOLERANCE``), else straight lines
    quadratic curves  -> cubic curves (exactly), else straight lines
    dashed lines      -> one plain path per dash
    even-odd fills    -> the same subpaths, turned so that the nonzero rule fills
                         the same area (outlines that cross are recomputed)
    group transforms  -> applied to the children's numbers; stroke widths and
                         dashes scale by the transform's area factor
    formulas          -> their glyph outlines, filled, where TeX cannot be set

What cannot be rewritten is reported in IR terms, naming the object and
never the backend; the agent fixes the IR, not the choice of backend:

    E-CAPABILITY   a text where texts cannot be drawn; a text, formula or
                   image that a group turns or stretches where transforms
                   cannot be drawn (and that has no outlines); an image
    E-ENVIRONMENT  a formula with no glyph outlines where TeX cannot be set
                   (it was measured without typesetting)
"""

import math
from collections.abc import Iterable, Sequence
from typing import Final

from shapely.geometry import LineString, Point, Polygon

from irpipe.backends.base import E_CAPABILITY, E_ENVIRONMENT, Capability
from irpipe.canvas import units
from irpipe.core import Issue
from irpipe.frontend import shapes
from irpipe.frontend.geometry import affine, areas, curves
from irpipe.frontend.geometry.affine import XY, Matrix
from irpipe.frontend.geometry.curves import Piece
from irpipe.schema import lir

TOLERANCE: Final = 0.001
"""Units a lowered curve may stray from the original (about a tenth of a pixel at 1080p)."""


def lower(
    drawing: lir.LIRDocument, capabilities: Iterable[Capability]
) -> tuple[lir.LIRDocument, list[Issue]]:
    """``drawing`` with only ``capabilities``' features, and what could not be lowered."""
    lowering = _Lowering(frozenset(capabilities))
    items = tuple(lowering.group(item, affine.IDENTITY) for item in drawing.items)
    return drawing.model_copy(update={"items": items}), lowering.problems


class _Lowering:
    def __init__(self, can: frozenset[Capability]) -> None:
        self.can = can
        self.problems: list[Issue] = []

    def group(self, group: lir.Group, pending: Matrix) -> lir.Group:
        """The group lowered; ``pending`` is the transform folded in from the groups above."""
        if Capability.TRANSFORM in self.can:
            transform, inner = group.transform, pending
        else:
            transform, inner = affine.IDENTITY, affine.compose(pending, group.transform)
        children: list[lir.Node] = []
        for node in group.children:
            if isinstance(node, lir.Group):
                children.append(self.group(node, inner))
            else:
                children.extend(self.item(node, inner, group))
        return group.model_copy(update={"transform": transform, "children": tuple(children)})

    def item(self, node: lir.Node, m: Matrix, owner: lir.Group) -> list[lir.Node]:
        if isinstance(node, lir.PathItem):
            return self.path(node, m)
        if isinstance(node, lir.TextItem):
            return self.text(node, m, owner)
        if isinstance(node, lir.MathItem):
            return self.math(node, m, owner)
        if isinstance(node, lir.ImageItem):
            return self.image(node, m, owner)
        raise TypeError(f"cannot lower {type(node).__name__}")

    # -- paths --------------------------------------------------------------

    def path(self, item: lir.PathItem, m: Matrix) -> list[lir.Node]:
        subpaths, hint, stroke = item.subpaths, item.hint, item.stroke
        if m != affine.IDENTITY:
            subpaths = curves.transform(subpaths, m)
            hint = shapes.mapped_hint(hint, m) if _axis_aligned(m) else None
            if stroke is not None:
                stroke = _scaled(stroke, _scale(m))
        subpaths = tuple(self.curves(subpaths))
        fill_subpaths, fill = subpaths, item.fill
        if fill is not None and fill.rule == "evenodd" and Capability.EVENODD not in self.can:
            fill_subpaths = _nonzero(subpaths)
            fill = fill.model_copy(update={"rule": "nonzero"})
        stroke_subpaths = subpaths
        if stroke is not None and stroke.dash and Capability.DASH not in self.can:
            stroke_subpaths = _dashes(subpaths, [units(d) for d in stroke.dash])
            stroke = stroke.model_copy(update={"dash": None})
        if fill_subpaths is stroke_subpaths or fill is None or stroke is None:
            drawn = fill_subpaths if stroke is None else stroke_subpaths
            if not drawn:
                return []
            return [item.model_copy(update={"subpaths": drawn, "fill": fill, "stroke": stroke,
                                            "hint": hint})]  # fmt: skip
        parts: list[lir.Node] = [
            lir.PathItem(subpaths=fill_subpaths, fill=fill, hint=hint, depth=item.depth)
        ]
        if stroke_subpaths:
            parts.append(lir.PathItem(subpaths=stroke_subpaths, stroke=stroke, depth=item.depth))
        return parts

    def curves(self, subpaths: Iterable[lir.Subpath]) -> Iterable[lir.Subpath]:
        """Each subpath with the curve kinds the backend lacks rewritten."""
        quads, cubics = Capability.QUADRATIC in self.can, Capability.CUBIC in self.can
        for subpath in subpaths:
            segments: list[lir.Segment] = []
            current = subpath.start
            for segment in subpath.segments:
                match segment:
                    case lir.CubicTo(cubic=(c1, c2, p)) if not cubics:
                        cubic: Piece = (current, c1, c2, p)
                        segments += _cubic_as_quads(cubic) if quads else _as_lines(cubic)
                    case lir.QuadTo(quad=(c, p)) if not quads:
                        quad: Piece = (current, c, p)
                        segments += [_quad_as_cubic(quad)] if cubics else _as_lines(quad)
                    case _:
                        segments.append(segment)
                current = _end(segment)
            yield subpath.model_copy(update={"segments": tuple(segments)})

    # -- texts, formulas, images ----------------------------------------------

    def text(self, item: lir.TextItem, m: Matrix, owner: lir.Group) -> list[lir.Node]:
        if Capability.TEXT not in self.can:
            self.problems.append(
                E_CAPABILITY(
                    f"'{owner.id}' is a text, and texts cannot be drawn in this picture's output",
                    path=owner.source,
                    objects=[owner.id],
                    hint="write the words as a formula (\\text{...}); a formula can be drawn "
                    "from its outlines",
                )
            )
            return []
        if m == affine.IDENTITY:
            return [item]
        if not _similar(m):
            self._turned(owner, "a text")
            return []
        return [_moved_box(item, m)]

    def math(self, item: lir.MathItem, m: Matrix, owner: lir.Group) -> list[lir.Node]:
        typeset = Capability.MATH in self.can
        if typeset and (m == affine.IDENTITY or _similar(m)):
            if m == affine.IDENTITY:
                return [item]
            moved = _moved_box(item, m)
            return [moved.model_copy(update={"glyphs": curves.transform(item.glyphs, m)})]
        if item.glyphs:
            glyphs = tuple(self.curves(curves.transform(item.glyphs, m)))
            fill = lir.FillPaint(color=item.color, opacity=item.opacity)
            return [lir.PathItem(subpaths=glyphs, fill=fill, depth=item.depth)]
        if not typeset:
            self.problems.append(
                E_ENVIRONMENT(
                    f"formula '{owner.id}' has no glyph outlines, and this picture's output "
                    "cannot set TeX",
                    path=owner.source,
                    objects=[owner.id],
                    hint='formulas were measured without typesetting; measure with "pango" '
                    "([options.measure] metrics in pipeline.toml)",
                )
            )
        else:
            self._turned(owner, "a formula")
        return []

    def image(self, item: lir.ImageItem, m: Matrix, owner: lir.Group) -> list[lir.Node]:
        if Capability.IMAGE not in self.can:
            self.problems.append(
                E_CAPABILITY(
                    f"'{owner.id}' is an image, and images cannot be drawn in this picture's "
                    "output",
                    path=owner.source,
                    objects=[owner.id],
                    hint="draw it with shapes and paths instead",
                )
            )
            return []
        if m == affine.IDENTITY:
            return [item]
        if not _similar(m):
            self._turned(owner, "an image")
            return []
        return [item.model_copy(update={"box": affine.transform_box(m, item.box)})]

    def _turned(self, owner: lir.Group, what: str) -> None:
        self.problems.append(
            E_CAPABILITY(
                f"'{owner.id}' is {what} that a group turns or stretches, which this "
                "picture's output cannot draw",
                path=owner.source,
                objects=[owner.id],
                hint="keep it out of turned or unevenly scaled groups; only shapes and "
                "formulas with outlines can be turned here",
            )
        )


# -- matrices -----------------------------------------------------------------


def _axis_aligned(m: Matrix) -> bool:
    a, b, c, d, _, _ = m
    return b == 0 and c == 0 and a > 0 and d > 0


def _similar(m: Matrix) -> bool:
    """A shift and an even, unturned scale: what a text box can follow."""
    return _axis_aligned(m) and math.isclose(m[0], m[3])


def _scale(m: Matrix) -> float:
    """How much ``m`` scales lengths, on average (the square root of its area factor)."""
    a, b, c, d, _, _ = m
    return math.sqrt(abs(a * d - b * c))


def _scaled(stroke: lir.StrokePaint, factor: float) -> lir.StrokePaint:
    dash = tuple(d * factor for d in stroke.dash) if stroke.dash else stroke.dash
    return stroke.model_copy(update={"width": stroke.width * factor, "dash": dash})


def _moved_box[T: (lir.TextItem, lir.MathItem)](item: T, m: Matrix) -> T:
    """A text or formula carried by a shift and an even scale."""
    at = affine.apply(m, item.at)
    return item.model_copy(
        update={
            "at": at,
            "box": affine.transform_box(m, item.box),
            "baseline": affine.apply(m, (item.at[0], item.baseline))[1],
            "size": item.size * m[0],
        }
    )


# -- curves -----------------------------------------------------------------


def _end(segment: lir.Segment) -> XY:
    match segment:
        case lir.LineTo(line=p) | lir.QuadTo(quad=(_, p)) | lir.CubicTo(cubic=(_, _, p)):
            return p
    raise TypeError(segment)


def _quad_as_cubic(piece: Piece) -> lir.CubicTo:
    """The same curve, exactly: a quadratic is a cubic with its controls two thirds along."""
    p0, q, p2 = piece
    c1 = (p0[0] + 2 / 3 * (q[0] - p0[0]), p0[1] + 2 / 3 * (q[1] - p0[1]))
    c2 = (p2[0] + 2 / 3 * (q[0] - p2[0]), p2[1] + 2 / 3 * (q[1] - p2[1]))
    return lir.CubicTo(cubic=(c1, c2, p2))


def _cubic_as_quads(piece: Piece) -> list[lir.Segment]:
    """Quadratics within ``TOLERANCE`` of the cubic, one per equal slice of it.

    A cubic sliced in n is matched by quadratics whose control is the
    average of the slice's two extrapolated controls; the error falls as 1/n^3.
    """
    p0, c1, c2, p3 = piece
    third = math.dist((0.0, 0.0), _sub(_sub(p3, _mul(c2, 3)), _sub(p0, _mul(c1, 3))))
    error = math.sqrt(3) / 36 * third
    count = max(1, math.ceil((error / TOLERANCE) ** (1 / 3)))
    out: list[lir.Segment] = []
    for part in _slices(piece, count):
        a, b, c, e = part
        q = (
            (3 * (b[0] + c[0]) - a[0] - e[0]) / 4,
            (3 * (b[1] + c[1]) - a[1] - e[1]) / 4,
        )
        out.append(lir.QuadTo(quad=(q, e)))
    return out


def _as_lines(piece: Piece) -> list[lir.Segment]:
    """Straight segments that stray from the curve by at most ``TOLERANCE``."""
    if len(piece) == 3:
        bend = math.dist((0.0, 0.0), _sub(_add(piece[0], piece[2]), _mul(piece[1], 2)))
        count = max(1, math.ceil(math.sqrt(bend / (4 * TOLERANCE))))
    else:
        bends = [
            math.dist((0.0, 0.0), _sub(_add(piece[k], piece[k + 2]), _mul(piece[k + 1], 2)))
            for k in (0, 1)
        ]
        count = max(1, math.ceil(math.sqrt(0.75 * max(bends) / TOLERANCE)))
    return [lir.LineTo(line=curves.point(piece, k / count)) for k in range(1, count + 1)]


def _slices(piece: Piece, count: int) -> list[Piece]:
    """The piece cut into ``count`` slices of equal parameter."""
    out: list[Piece] = []
    rest = piece
    for k in range(count, 1, -1):
        first, rest = curves.split(rest, 1 / k)
        out.append(first)
    out.append(rest)
    return out


def _add(p: XY, q: XY) -> XY:
    return (p[0] + q[0], p[1] + q[1])


def _sub(p: XY, q: XY) -> XY:
    return (p[0] - q[0], p[1] - q[1])


def _mul(p: XY, k: float) -> XY:
    return (p[0] * k, p[1] * k)


# -- dashes and fill rules ------------------------------------------------------


def _dashes(subpaths: Sequence[lir.Subpath], pattern: list[float]) -> tuple[lir.Subpath, ...]:
    """Each dash of the pattern as an open subpath, as SVG lays them out.

    The pattern (on, off, on, off...; repeated once more when its count is
    odd) starts afresh on each subpath and runs on across its segments,
    the closing edge of a closed subpath included.
    """
    if len(pattern) % 2:
        pattern = pattern * 2
    out: list[lir.Subpath] = []
    for subpath in subpaths:
        index, left = 0, pattern[0]
        dash: list[Piece] = []
        for piece in curves.pieces(subpath):
            length, done = curves.length(piece), 0.0
            while length - done > 1e-12:
                step = min(left, length - done)
                if index % 2 == 0:
                    dash.append(_part(piece, done, done + step))
                done += step
                left -= step
                if left <= 1e-12:
                    if dash:
                        out.append(curves.subpath_of(dash))
                        dash = []
                    index = (index + 1) % len(pattern)
                    left = pattern[index]
        if dash:
            out.append(curves.subpath_of(dash))
    return tuple(out)


def _part(piece: Piece, start: float, end: float) -> Piece:
    """The stretch of a piece between two distances along it."""
    t0 = curves.parameter_at(piece, start)
    t1 = curves.parameter_at(piece, end)
    rest = curves.split(piece, t0)[1] if t0 > 0 else piece
    if t1 >= 1:
        return rest
    return curves.split(rest, (t1 - t0) / (1 - t0))[0]


def _nonzero(subpaths: Sequence[lir.Subpath]) -> tuple[lir.Subpath, ...]:
    """Subpaths that fill under the nonzero rule what ``subpaths`` fill under even-odd.

    Outlines that do not cross keep their curves: a subpath inside an even
    number of others runs counterclockwise, inside an odd number clockwise.
    Outlines that cross are recomputed as polygons with their holes.
    """
    rings = [curves.flatten(s) for s in subpaths]
    lines = [LineString(ring) for ring in rings if len(ring) >= 2]
    if any(a.intersects(b) for k, a in enumerate(lines) for b in lines[k + 1 :]):
        return areas.subpaths(areas.area(subpaths, "evenodd"))
    outlines = [Polygon(ring) if len(ring) >= 4 else None for ring in rings]
    out: list[lir.Subpath] = []
    for k, (subpath, ring) in enumerate(zip(subpaths, rings, strict=True)):
        inside = sum(
            1
            for j, other in enumerate(outlines)
            if j != k and other is not None and other.contains(Point(ring[0]))
        )
        counterclockwise = areas.signed_area(ring) > 0
        out.append(subpath if counterclockwise == (inside % 2 == 0) else curves.reverse(subpath))
    return tuple(out)
