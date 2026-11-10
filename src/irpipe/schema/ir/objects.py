"""The drawable objects of IR 1.0's core: basic shapes, path, text, math and group.

Basic shapes: circle, ellipse, rect, regular_polygon, polygon, sector (closed,
so they can be filled) and line, polyline, arc (open, drawn as lines only).
The front-end turns every shape into a LIR path, so a backend never has to
know any of them; it gets the shape's name as a hint and may use its own
class for it (docs/SEMANTICS.md). Angles are degrees, counterclockwise from
the positive x axis.

    {"id": "c", "type": "circle", "center": [0, 0], "radius": 1.5, "color": "a"}

Every object has an ``id`` and a ``type``; the type selects the model. Paint
fields left out (``None``) are inherited: theme, then the style classes the
object names, then the object itself (docs/SEMANTICS.md). ``"none"`` as a
color means no paint at all.

A point may be a reference (``"v.tip"``, ``{"on": "f", "t": 0.5}``), and an
object may name a coordinate space with ``in``; the place stage resolves both
(docs/SEMANTICS.md, "Placement"). Texts, formulas and stacks are boxes: they
sit at a point, beside a point, or next to another object. Shapes may carry
a ``label`` and open ones ``arrows``.

A ``region`` is an area built from other shapes with set operations, and a
``flood_fill`` the part of the plane that lines enclose around a seed
(regions.py, analysis §2.6). Any object may be drawn only inside an area
(``clip``) or only outside one (``clip_out``).
"""

from typing import Annotated, Literal, Self

from pydantic import Field, PositiveFloat, PositiveInt, model_validator

from irpipe.schema.base import StrictModel
from irpipe.schema.color import ColorRef
from irpipe.schema.ir.common import (
    XY,
    Anchor,
    Direction,
    Id,
    Name,
    NonNegativeNumber,
    Number,
    Point,
    PositiveNumber,
    Size,
)
from irpipe.schema.ir.regions import RegionShape

Opacity = Annotated[float, Field(ge=0, le=1)]


class ObjectBase(StrictModel):
    """Fields every object has.

    ``style`` names one or more style classes from the header. ``z`` reorders
    drawing (higher is drawn later; ties keep list order). ``tags`` record what
    a generated shape means (``"spring"``); ``covers`` names the brief's
    ``must_show`` items the object shows. ``clip`` draws the object only
    inside an area, ``clip_out`` only outside one; lines and fills are cut,
    texts and formulas are drawn whole.
    """

    id: Id
    type: str
    style: Name | tuple[Name, ...] | None = None
    opacity: Opacity | None = None
    z: float | None = None
    tags: tuple[str, ...] = ()
    covers: tuple[str, ...] = ()
    clip: RegionShape | None = None
    clip_out: RegionShape | None = None

    @property
    def style_names(self) -> tuple[str, ...]:
        if self.style is None:
            return ()
        return (self.style,) if isinstance(self.style, str) else self.style


class InSpace(ObjectBase):
    """An object whose numbers may be read in a coordinate space (``"in": "P"``).

    The space maps the object's points and lengths to the frame; stroke
    widths and type sizes stay in reference pixels.
    """

    space: Name | None = Field(default=None, alias="in")


class Label(StrictModel):
    """A text or formula that belongs to a shape and is drawn beside one of its points.

    ``at`` names the owner's anchor (``"tip"``, ``"center"``, ``"right_top"``).
    With ``dir`` the label sits beside that point, ``gap`` away; without it,
    it is centered on the point. It is drawn as the object ``<owner>.label``,
    in the owner's color unless it says otherwise, at the ``label`` size.
    """

    text: str | None = Field(default=None, min_length=1)
    tex: str | None = Field(default=None, min_length=1)
    at: str = Field(default="center", pattern=r"^[a-z_]+$")
    dir: Direction | None = None
    gap: NonNegativeNumber | None = None
    size: Size | None = None
    color: ColorRef | None = None
    weight: Literal["regular", "bold"] | None = None
    italic: bool | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.text is None) == (self.tex is None):
            raise ValueError("a label has either text or tex")
        if self.gap is not None and self.dir is None:
            raise ValueError("gap is the distance beside the point; it needs dir")
        if self.tex is not None and (self.weight is not None or self.italic is not None):
            raise ValueError("weight and italic are for a text label; TeX sets its own")
        return self


class Stroked(InSpace):
    """An object drawn with a line: its color, width and dash pattern."""

    color: ColorRef | None = None
    stroke_width: PositiveFloat | None = None
    dash: tuple[PositiveFloat, ...] | None = None
    label: Label | None = None


ArrowPlace = Literal["start", "mid", "end"]


class Arrows(StrictModel):
    """Arrowheads on an open line: at its ``start``, its ``end``, or halfway along (``mid``).

    A head points the way the line runs (at the start, backwards) and is
    filled in the line's color; the line stops inside it. ``arrow_size`` is
    the head's length in reference pixels; it grows with the stroke width
    when left out.
    """

    arrows: tuple[ArrowPlace, ...] = ()
    arrow_size: PositiveFloat | None = None

    @model_validator(mode="after")
    def _each_once(self) -> Self:
        if len(set(self.arrows)) != len(self.arrows):
            raise ValueError("each arrow place is listed once")
        return self


class Filled(Stroked):
    """A closed object: a line around it and a fill inside."""

    fill: ColorRef | None = None
    fill_opacity: Opacity | None = None


class Circle(Filled):
    type: Literal["circle"] = "circle"
    center: Point
    radius: PositiveNumber


class Ellipse(Filled):
    """An axis-aligned ellipse with radii ``rx`` and ``ry``; turn it with a group."""

    type: Literal["ellipse"] = "ellipse"
    center: Point
    rx: PositiveNumber
    ry: PositiveNumber


class Rect(Filled):
    """An axis-aligned rectangle; turn it with a group."""

    type: Literal["rect"] = "rect"
    center: Point
    width: PositiveNumber
    height: PositiveNumber
    corner_radius: NonNegativeNumber = 0


class RegularPolygon(Filled):
    """``sides`` corners on a circle of ``radius`` around ``center``.

    With ``rotation`` 0 it stands on a flat bottom edge (a triangle points up,
    a square is axis-aligned); ``rotation`` turns it counterclockwise.
    """

    type: Literal["regular_polygon"] = "regular_polygon"
    center: Point
    radius: PositiveNumber
    sides: int = Field(ge=3, le=64)
    rotation: Number = 0


class Polygon(Filled):
    """A closed outline through ``points``, in order."""

    type: Literal["polygon"] = "polygon"
    points: tuple[Point, ...] = Field(min_length=3)


class Line(Stroked, Arrows):
    type: Literal["line"] = "line"
    start: Point
    end: Point


class Polyline(Stroked, Arrows):
    """An open line through ``points``, in order."""

    type: Literal["polyline"] = "polyline"
    points: tuple[Point, ...] = Field(min_length=2)


def check_sweep(start_angle: float, end_angle: float) -> None:
    """An arc goes from ``start_angle`` to ``end_angle``: not nowhere, at most once around."""
    sweep = end_angle - start_angle
    if sweep == 0:
        raise ValueError("start_angle and end_angle are equal, so the arc has no length")
    if abs(sweep) > 360:
        raise ValueError(f"the arc sweeps {abs(sweep):g} degrees; at most 360 is allowed")


class Arc(Stroked, Arrows):
    """Part of a circle, from ``start_angle`` to ``end_angle``.

    The arc runs counterclockwise when ``end_angle`` is larger, clockwise
    when it is smaller.
    """

    type: Literal["arc"] = "arc"
    center: Point
    radius: PositiveNumber
    start_angle: Number
    end_angle: Number

    @model_validator(mode="after")
    def _sweeps(self) -> Self:
        check_sweep(self.start_angle, self.end_angle)
        return self


class Sector(Filled):
    """A slice of a disc: the arc from ``start_angle`` to ``end_angle`` and two radii."""

    type: Literal["sector"] = "sector"
    center: Point
    radius: PositiveNumber
    start_angle: Number
    end_angle: Number

    @model_validator(mode="after")
    def _sweeps(self) -> Self:
        check_sweep(self.start_angle, self.end_angle)
        return self


class LineTo(StrictModel):
    line: Point


class QuadTo(StrictModel):
    quad: tuple[Point, Point]
    """Control point, end point."""


class CubicTo(StrictModel):
    cubic: tuple[Point, Point, Point]
    """First control point, second control point, end point."""


Segment = LineTo | QuadTo | CubicTo


class Subpath(StrictModel):
    """One pen stroke: a start point and the segments that follow it."""

    start: Point
    segments: tuple[Segment, ...] = Field(min_length=1)
    closed: bool = False


class Path(Filled, Arrows):
    """Straight and Bezier segments, in one or more subpaths (holes are subpaths)."""

    type: Literal["path"] = "path"
    subpaths: tuple[Subpath, ...] = Field(min_length=1)
    fill_rule: Literal["nonzero", "evenodd"] = "nonzero"


class Placed(ObjectBase):
    """Where a box (a text, a formula or a stack) goes. One of three ways:

    - ``at`` and ``anchor``: the ``anchor`` point of the box sits at ``at``
      (``center`` when left out);
    - ``at`` and ``dir``: the box sits beside the point ``at``, in direction
      ``dir``, ``gap`` away from it;
    - ``next_to`` and ``dir``: the box sits beside another object's box,
      ``gap`` away (``dir`` is ``right`` when left out).

    A box inside a stack gives none of them; the stack places it.
    """

    at: Point | None = None
    anchor: Anchor | None = None
    next_to: Id | None = None
    dir: Direction | None = None
    gap: NonNegativeNumber | None = None

    @model_validator(mode="after")
    def _one_way_to_place(self) -> Self:
        if self.at is not None and self.next_to is not None:
            raise ValueError("give at or next_to, not both")
        if self.anchor is not None and self.dir is not None:
            raise ValueError(
                "anchor puts a point of the box on at; dir puts the box beside it; give one"
            )
        if self.anchor is not None and self.next_to is not None:
            raise ValueError("next_to places the box with dir and gap, not with anchor")
        if self.gap is not None and self.dir is None and self.next_to is None:
            raise ValueError("gap is the distance beside a point or object; it needs dir")
        return self


class Text(InSpace, Placed):
    type: Literal["text"] = "text"
    text: str = Field(min_length=1)
    size: Size | None = None
    color: ColorRef | None = None
    weight: Literal["regular", "bold"] | None = None
    italic: bool | None = None


class Math(InSpace, Placed):
    """A formula in TeX, set in display style and placed like a text.

    ``tex`` is what goes between the dollars: ``"\\frac{a}{b}"``. The
    front-end typesets it before anything is drawn, so a TeX mistake is
    reported (E-TEX) with this object's path.
    """

    type: Literal["math"] = "math"
    tex: str = Field(min_length=1)
    size: Size | None = None
    color: ColorRef | None = None


class Group(ObjectBase):
    """Objects that move together.

    ``children`` are ids of other objects. The transform scales and rotates
    them about ``pivot`` (degrees, counterclockwise), then translates them;
    it turns and scales their drawings too, strokes and texts included. The
    group's opacity multiplies each child's.
    """

    type: Literal["group"] = "group"
    children: tuple[Id, ...] = Field(min_length=1)
    translate: XY = (0, 0)
    rotate: Number = 0
    scale: PositiveNumber | tuple[PositiveNumber, PositiveNumber] = 1
    pivot: Point = (0, 0)


class Stack(Placed):
    """Objects laid out in a column, a row or a grid, as one box (analysis §2.8).

    ``children`` are ids of other objects, in reading order; a grid fills
    rows of ``columns`` children, left to right, top to bottom. Each child
    sits in its cell so that its ``align`` point meets the cell's: ``left_center``
    lines a column up on the left, ``center_baseline`` a row on its
    baselines. ``spacing`` is the room between cells: one number, or
    ``[between columns, between rows]``. The stack itself is placed like a
    text; its baseline is its first row's.
    """

    type: Literal["stack"] = "stack"
    children: tuple[Id, ...] = Field(min_length=1)
    arrange: Literal["column", "row", "grid"] = "column"
    columns: PositiveInt | None = None
    spacing: NonNegativeNumber | tuple[NonNegativeNumber, NonNegativeNumber] = 0.25
    align: Anchor = "center"

    @model_validator(mode="after")
    def _columns_for_grid(self) -> Self:
        if (self.arrange == "grid") != (self.columns is not None):
            raise ValueError('a grid needs columns, and only "arrange": "grid" takes them')
        return self


Container = Group | Stack
"""An object whose ``children`` are other objects."""


class Region(Filled):
    """An area built from other shapes: ``{"difference": ["A", "B"]}`` (regions.py).

    Its operands are often defs, which are not drawn themselves. A region is
    not outlined unless it gives a ``color``.
    """

    type: Literal["region"] = "region"
    shape: RegionShape


class FloodFill(Filled):
    """The part of the plane around ``seed`` that the lines of ``bounded_by`` enclose.

    Like a paint bucket: the boundaries may be open lines (a parabola, a
    line and an axis); together they must close the part the seed is in.
    It is not outlined unless it gives a ``color``.
    """

    type: Literal["flood_fill"] = "flood_fill"
    seed: Point
    bounded_by: tuple[Id, ...] = Field(min_length=1)


Area = Region | FloodFill
"""Objects whose outline the front-end computes from other objects."""

Shape = Circle | Ellipse | Rect | RegularPolygon | Polygon | Sector | Line | Polyline | Arc | Path
"""Every object that is drawn as a path."""

Open = Line | Polyline | Arc | Path
"""Shapes with a start and an end, which may carry arrowheads."""

IRObject = Annotated[
    Shape | Region | FloodFill | Text | Math | Group | Stack, Field(discriminator="type")
]
"""Any core object; ``type`` picks the model."""
