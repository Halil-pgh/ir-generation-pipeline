"""Stage "resolve": turns the placed, measured IR into LIR, the list backends draw.

    requires  ir_placed   every position as numbers (place)
              measured    every text's and formula's box (measure)
    provides  lir         the LIRDocument backends draw

Every IR object becomes one LIR group with its id. An object inside a group
is drawn inside that group, at the group's place in the list. Siblings are
sorted by ``z`` (ties keep list order). Paint is read from each object as
normalize wrote it, and opacity is multiplied down through groups.

An object drawn in a space has its points mapped by the space here, so its
geometry is exact and its stroke width untouched. Every text and formula is
placed by its measured box; a formula carries its glyph outlines. Arrowheads
are filled triangles in the line's color, and the line stops inside them.
``defs`` are not drawn.
"""

from collections.abc import Sequence
from typing import Final, Protocol

from irpipe.artifacts import IR_PLACED, LIR, MEASURED
from irpipe.canvas import units
from irpipe.core import STAGES, Stage, StageContext
from irpipe.frontend import layout, shapes
from irpipe.frontend.anchors import xy
from irpipe.frontend.geometry import affine, curves
from irpipe.frontend.geometry.affine import Matrix
from irpipe.frontend.labels import source_paths
from irpipe.frontend.paint import Paint, painted, to_hex
from irpipe.metrics import MathBox, TextBox
from irpipe.metrics.svgpath import Subpath
from irpipe.schema import lir
from irpipe.schema.ir import Group, IRDocument, Line, Math, Open, Polyline, Shape, Stack, Text
from irpipe.schema.ir.objects import ObjectBase

ARROW_TRIM: Final = 0.6
"""How far, as a share of the head's length, the line stops short of an arrow's tip."""


def arrow_length(stroke_width: float) -> float:
    """An arrowhead's length in reference px when ``arrow_size`` is left out."""
    return 4 * stroke_width + 10


@STAGES.register
class Resolve(Stage):
    name = "resolve"
    requires = (IR_PLACED, MEASURED)
    provides = (LIR,)

    def run(self, ctx: StageContext) -> None:
        measured = ctx.read(MEASURED)
        ctx.write(LIR, Resolver(ctx.read(IR_PLACED), measured).resolve())


class Resolver:
    """Builds the LIR of one placed document from its measurements."""

    def __init__(self, document: IRDocument, measured: dict[str, TextBox]) -> None:
        self._document = document
        self._measured = measured
        self._objects = {obj.id: obj for obj in document.objects}
        self._sources = source_paths(document)
        self._in_group = {
            child for obj in document.objects if isinstance(obj, Group) for child in obj.children
        }
        self._spaces: dict[str, Matrix] = {}
        for space in document.spaces:
            (ox, oy), (ux, uy) = xy(space.origin), space.units
            self._spaces[space.id] = (ux, 0.0, 0.0, uy, ox, oy)

    def resolve(self) -> lir.LIRDocument:
        frame = self._document.frame
        top = [obj for obj in self._document.objects if obj.id not in self._in_group]
        return lir.LIRDocument(
            canvas=lir.LIRCanvas(
                units=frame.units, pixels=frame.pixels, background=to_hex(frame.background)
            ),
            items=tuple(self._group(obj, 1.0) for obj in _by_z(top)),
        )

    def _group(self, obj: ObjectBase, opacity: float) -> lir.Group:
        paint = painted(obj)
        alpha = opacity * paint.opacity
        source = self._sources[obj.id]
        if isinstance(obj, Group):
            members = [self._objects[c] for c in obj.children]
            return lir.Group(
                id=obj.id,
                source=source,
                transform=shapes.group_matrix(obj),
                z=obj.z or 0,
                children=tuple(self._group(m, alpha) for m in _by_z(members)),
            )
        if isinstance(obj, Stack):
            raise TypeError(f"stack '{obj.id}' reached resolve; the place stage makes it a group")
        assert isinstance(obj, Shape | Text | Math)
        return lir.Group(
            id=obj.id, source=source, z=obj.z or 0, children=self._draw(obj, paint, alpha)
        )

    def _draw(self, obj: Shape | Text | Math, paint: Paint, alpha: float) -> tuple[lir.Node, ...]:
        if isinstance(obj, Text):
            color = paint.color
            return () if color is None else (self._text(obj, paint, color, alpha),)
        if isinstance(obj, Math):
            color = paint.color
            return () if color is None else (self._math(obj, paint, color, alpha),)
        subpaths, hint, rule = shapes.outline(obj)
        space = self._space(obj)
        if space != affine.IDENTITY:
            subpaths, hint = curves.transform(subpaths, space), shapes.mapped_hint(hint, space)
        heads: tuple[lir.Subpath, ...] = ()
        if isinstance(obj, Open) and obj.arrows and paint.color is not None:
            subpaths, hint, heads = _with_arrows(obj, subpaths, hint, paint)
        drawn: list[lir.Node] = []
        line = _path(subpaths, paint, alpha, hint, rule)
        if line is not None:
            drawn.append(line)
        if heads and paint.color is not None:
            fill = lir.FillPaint(color=paint.color, opacity=alpha)
            drawn.append(lir.PathItem(subpaths=heads, fill=fill))
        return tuple(drawn)

    def _space(self, obj: ObjectBase) -> Matrix:
        name = getattr(obj, "space", None)
        return affine.IDENTITY if name is None else self._spaces[name]

    def _placed_box(self, obj: Text | Math) -> tuple[tuple[float, float], lir.Box, float]:
        """Where the text's anchor is drawn, its box and its baseline."""
        at = affine.apply(self._space(obj), xy(obj.at or (0, 0)))
        box = self._measured[obj.id]
        bounds, baseline = layout.box_at(
            at, obj.anchor or "center", units(box.width), units(box.ascent), units(box.descent)
        )
        return at, bounds, baseline

    def _text(self, text: Text, paint: Paint, color: str, alpha: float) -> lir.TextItem:
        at, bounds, baseline = self._placed_box(text)
        return lir.TextItem(
            text=text.text,
            font=self._document.typography.text_font,
            size=paint.size,
            weight=paint.weight,
            italic=paint.italic,
            color=color,
            opacity=alpha,
            at=at,
            anchor=text.anchor or "center",
            box=bounds,
            baseline=baseline,
        )

    def _math(self, formula: Math, paint: Paint, color: str, alpha: float) -> lir.MathItem:
        at, bounds, baseline = self._placed_box(formula)
        box = self._measured[formula.id]
        outlines = box.outlines if isinstance(box, MathBox) else ()
        return lir.MathItem(
            tex=formula.tex,
            size=paint.size,
            color=color,
            opacity=alpha,
            at=at,
            anchor=formula.anchor or "center",
            box=bounds,
            baseline=baseline,
            glyphs=tuple(_glyph(s, bounds[0], baseline) for s in outlines),
        )


def _with_arrows(
    obj: Open,
    subpaths: tuple[lir.Subpath, ...],
    hint: lir.ShapeHint | None,
    paint: Paint,
) -> tuple[tuple[lir.Subpath, ...], lir.ShapeHint | None, tuple[lir.Subpath, ...]]:
    """The line cut back for its arrowheads, its hint, and the heads.

    A line or polyline keeps a hint with its cut points; any other shape
    goes without one, as its hint would no longer match the path.
    """
    length = units(obj.arrow_size or arrow_length(paint.stroke_width))
    heads: list[lir.Subpath] = []
    if "start" in obj.arrows:
        dx, dy = curves.start_direction(subpaths)
        heads.append(shapes.arrowhead(subpaths[0].start, (-dx, -dy), length))
    if "mid" in obj.arrows:
        (x, y), (dx, dy) = curves.point_at(subpaths, 0.5)
        heads.append(shapes.arrowhead((x + dx * length / 2, y + dy * length / 2), (dx, dy), length))
    if "end" in obj.arrows:
        heads.append(
            shapes.arrowhead(curves.end_point(subpaths), curves.end_direction(subpaths), length)
        )
    cut = ARROW_TRIM * length
    trimmed = curves.trim(
        subpaths, cut if "start" in obj.arrows else 0, cut if "end" in obj.arrows else 0
    )
    points = [trimmed[0].start, *(piece[-1] for piece in curves.pieces(trimmed[0]))]
    new_hint: lir.ShapeHint | None = None
    if isinstance(obj, Line) and hint is not None:
        new_hint = lir.LineHint(start=points[0], end=points[-1])
    elif isinstance(obj, Polyline) and hint is not None:
        new_hint = lir.PolylineHint(points=tuple(points))
    return trimmed, new_hint, tuple(heads)


def _glyph(outline: Subpath, left: float, baseline: float) -> lir.Subpath:
    """A glyph outline (reference px from the box's origin) placed on the frame, in units."""

    def place(point: tuple[float, float]) -> tuple[float, float]:
        return (left + units(point[0]), baseline + units(point[1]))

    segments: list[lir.Segment] = []
    for kind, points in outline.segments:
        placed = tuple(place(p) for p in points)
        if kind == "line":
            segments.append(lir.LineTo(line=placed[0]))
        elif kind == "quad":
            segments.append(lir.QuadTo(quad=(placed[0], placed[1])))
        else:
            segments.append(lir.CubicTo(cubic=(placed[0], placed[1], placed[2])))
    return lir.Subpath(start=place(outline.start), segments=tuple(segments), closed=outline.closed)


def _path(
    subpaths: tuple[lir.Subpath, ...],
    paint: Paint,
    alpha: float,
    hint: lir.ShapeHint | None,
    rule: shapes.FillRule,
) -> lir.PathItem | None:
    """A path with the paint it has, or None when it paints nothing."""
    fill = stroke = None
    if paint.fill is not None:
        fill = lir.FillPaint(color=paint.fill, opacity=alpha * paint.fill_opacity, rule=rule)
    if paint.color is not None:
        stroke = lir.StrokePaint(
            color=paint.color, opacity=alpha, width=paint.stroke_width, dash=paint.dash
        )
    if fill is None and stroke is None:
        return None
    return lir.PathItem(subpaths=subpaths, fill=fill, stroke=stroke, hint=hint)


class _Layered(Protocol):
    @property
    def z(self) -> float | None: ...


def _by_z[T: _Layered](items: Sequence[T]) -> list[T]:
    """Stable sort by z; an object without z counts as 0."""
    return sorted(items, key=lambda item: item.z or 0)
