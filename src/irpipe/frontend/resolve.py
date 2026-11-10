"""Stage "resolve": turns a normalized, measured IR with absolute positions into LIR.

    requires  ir_normal   the IR with every object's paint written out (normalize)
              measured    every text's and formula's box (measure)
    provides  lir         the LIRDocument backends draw

Every IR object becomes one LIR group with its id. An object inside a group
is drawn inside that group, at the group's place in the list. Siblings are
sorted by ``z`` (ties keep list order). Paint is read from each object as
normalize wrote it, opacity is multiplied down through groups, and every
text and formula is placed by its measured box; a formula carries its glyph
outlines. ``defs`` are not drawn.

This first resolve takes positions as written; references such as
``"v.tip"``, spaces and labels come with step 11.
"""

from collections.abc import Sequence
from typing import Protocol

from irpipe.artifacts import IR_NORMAL, LIR, MEASURED
from irpipe.canvas import units
from irpipe.core import STAGES, Stage, StageContext
from irpipe.frontend import shapes
from irpipe.frontend.paint import Paint, painted, to_hex
from irpipe.metrics import MathBox, TextBox
from irpipe.metrics.svgpath import Subpath
from irpipe.schema import lir
from irpipe.schema.ir import Group, IRDocument, Math, Shape, Text


@STAGES.register
class Resolve(Stage):
    name = "resolve"
    requires = (IR_NORMAL, MEASURED)
    provides = (LIR,)

    def run(self, ctx: StageContext) -> None:
        measured = ctx.read(MEASURED)
        ctx.write(LIR, Resolver(ctx.read(IR_NORMAL), measured).resolve())


class Resolver:
    """Builds the LIR of one normalized document from its measurements."""

    def __init__(self, document: IRDocument, measured: dict[str, TextBox]) -> None:
        self._document = document
        self._measured = measured
        self._index = {obj.id: k for k, obj in enumerate(document.objects)}
        self._in_group = {
            child for obj in document.objects if isinstance(obj, Group) for child in obj.children
        }

    def resolve(self) -> lir.LIRDocument:
        frame = self._document.frame
        top = [obj for obj in self._document.objects if obj.id not in self._in_group]
        return lir.LIRDocument(
            canvas=lir.LIRCanvas(
                units=frame.units, pixels=frame.pixels, background=to_hex(frame.background)
            ),
            items=tuple(self._group(obj, 1.0) for obj in _by_z(top)),
        )

    def _group(self, obj: Shape | Text | Math | Group, opacity: float) -> lir.Group:
        paint = painted(obj)
        alpha = opacity * paint.opacity
        source = f"objects[{self._index[obj.id]}]"
        if isinstance(obj, Group):
            members = [self._document.objects[self._index[c]] for c in obj.children]
            return lir.Group(
                id=obj.id,
                source=source,
                transform=shapes.group_matrix(obj),
                z=obj.z or 0,
                children=tuple(self._group(m, alpha) for m in _by_z(members)),
            )
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
        item = _path(subpaths, paint, alpha, hint, rule)
        return () if item is None else (item,)

    def _text(self, text: Text, paint: Paint, color: str, alpha: float) -> lir.TextItem:
        font = self._document.typography.text_font
        bounds, baseline = place_text(text.at, text.anchor, self._measured[text.id])
        return lir.TextItem(
            text=text.text,
            font=font,
            size=paint.size,
            weight=paint.weight,
            italic=paint.italic,
            color=color,
            opacity=alpha,
            at=text.at,
            anchor=text.anchor,
            box=bounds,
            baseline=baseline,
        )

    def _math(self, formula: Math, paint: Paint, color: str, alpha: float) -> lir.MathItem:
        box = self._measured[formula.id]
        bounds, baseline = place_text(formula.at, formula.anchor, box)
        outlines = box.outlines if isinstance(box, MathBox) else ()
        return lir.MathItem(
            tex=formula.tex,
            size=paint.size,
            color=color,
            opacity=alpha,
            at=formula.at,
            anchor=formula.anchor,
            box=bounds,
            baseline=baseline,
            glyphs=tuple(_glyph(s, bounds[0], baseline) for s in outlines),
        )


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


def place_text(at: tuple[float, float], anchor: str, box: TextBox) -> tuple[lir.Box, float]:
    """The box (in units) and baseline of a text whose ``anchor`` point sits at ``at``."""
    width, ascent, descent = units(box.width), units(box.ascent), units(box.descent)
    horizontal, _, vertical = ("center_center" if anchor == "center" else anchor).partition("_")
    x, y = at
    x0 = {"left": x, "center": x - width / 2, "right": x - width}[horizontal]
    baseline = {
        "top": y - ascent,
        "center": y - (ascent - descent) / 2,
        "baseline": y,
        "bottom": y + descent,
    }[vertical]
    return (x0, baseline - descent, x0 + width, baseline + ascent), baseline


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
