"""Stage "resolve": turns a checked IR with absolute positions into LIR.

    requires  ir      the IRDocument validate checked
    provides  lir     the LIRDocument backends draw
    options   metrics = "fixed"   the text measurer (irpipe/metrics)

Every IR object becomes one LIR group with its id. An object inside a group
is drawn inside that group, at the group's place in the list. Siblings are
sorted by ``z`` (ties keep list order). Paint goes through the cascade
(paint.py), opacity is multiplied down through groups, and every text is
measured to fill in its box and baseline. ``defs`` are not drawn.

This first resolve takes positions as written; references such as
``"v.tip"``, spaces and labels come with step 11.
"""

from collections.abc import Sequence
from dataclasses import replace
from typing import Protocol

from irpipe.artifacts import IR, LIR
from irpipe.canvas import units
from irpipe.core import STAGES, Stage, StageContext
from irpipe.frontend import shapes
from irpipe.frontend.paint import Paint, PaintResolver, to_hex
from irpipe.metrics import METRICS, TextBox, TextMetrics
from irpipe.schema import lir
from irpipe.schema.ir import Group, IRDocument, Shape, Text
from irpipe.schema.ir.objects import Filled

DEFAULT_METRICS = "fixed"


@STAGES.register
class Resolve(Stage):
    name = "resolve"
    requires = (IR,)
    provides = (LIR,)

    def run(self, ctx: StageContext) -> None:
        metrics = METRICS.get(str(ctx.options.get("metrics", DEFAULT_METRICS)))()
        ctx.write(LIR, Resolver(ctx.read(IR), metrics).resolve())


class Resolver:
    """Builds the LIR of one document."""

    def __init__(self, document: IRDocument, metrics: TextMetrics) -> None:
        self._document = document
        self._metrics = metrics
        self._paint = PaintResolver(document)
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

    def _group(self, obj: Shape | Text | Group, opacity: float) -> lir.Group:
        paint = self._paint.paint(obj)
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

    def _draw(self, obj: Shape | Text, paint: Paint, alpha: float) -> tuple[lir.Node, ...]:
        if isinstance(obj, Text):
            color = paint.color
            return () if color is None else (self._text(obj, paint, color, alpha),)
        subpaths, hint, rule = shapes.outline(obj)
        if not isinstance(obj, Filled):
            paint = replace(paint, fill=None)  # an open shape has no inside
        item = _path(subpaths, paint, alpha, hint, rule)
        return () if item is None else (item,)

    def _text(self, text: Text, paint: Paint, color: str, alpha: float) -> lir.TextItem:
        font = self._document.typography.text_font
        box = self._metrics.text(
            text.text, font=font, size=paint.size, weight=paint.weight, italic=paint.italic
        )
        bounds, baseline = place_text(text.at, text.anchor, box)
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
