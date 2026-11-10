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

This is the first subset. Expressions such as ``"44/17"`` (step 8), anchor
references such as ``"v.tip"``, coordinate spaces, labels, markers and math
(step 11) widen these types later.
"""

from typing import Annotated, Literal, Self

from pydantic import Field, PositiveFloat, model_validator

from irpipe.schema.base import StrictModel
from irpipe.schema.color import ColorRef
from irpipe.schema.ir.common import (
    Id,
    Name,
    NonNegativeNumber,
    Number,
    Point,
    PositiveNumber,
    Size,
)

Opacity = Annotated[float, Field(ge=0, le=1)]


class ObjectBase(StrictModel):
    """Fields every object has.

    ``style`` names one or more style classes from the header. ``z`` reorders
    drawing (higher is drawn later; ties keep list order). ``tags`` record what
    a generated shape means (``"spring"``); ``covers`` names the brief's
    ``must_show`` items the object shows.
    """

    id: Id
    type: str
    style: Name | tuple[Name, ...] | None = None
    opacity: Opacity | None = None
    z: float | None = None
    tags: tuple[str, ...] = ()
    covers: tuple[str, ...] = ()

    @property
    def style_names(self) -> tuple[str, ...]:
        if self.style is None:
            return ()
        return (self.style,) if isinstance(self.style, str) else self.style


class Stroked(ObjectBase):
    """An object drawn with a line: its color, width and dash pattern."""

    color: ColorRef | None = None
    stroke_width: PositiveFloat | None = None
    dash: tuple[PositiveFloat, ...] | None = None


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


class Line(Stroked):
    type: Literal["line"] = "line"
    start: Point
    end: Point


class Polyline(Stroked):
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


class Arc(Stroked):
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


class Path(Filled):
    """Straight and Bezier segments, in one or more subpaths (holes are subpaths)."""

    type: Literal["path"] = "path"
    subpaths: tuple[Subpath, ...] = Field(min_length=1)
    fill_rule: Literal["nonzero", "evenodd"] = "nonzero"


Anchor = Literal[
    "left_top",
    "center_top",
    "right_top",
    "left_center",
    "center",
    "right_center",
    "left_baseline",
    "center_baseline",
    "right_baseline",
    "left_bottom",
    "center_bottom",
    "right_bottom",
]
"""Which point of the text sits at ``at``: horizontal part, then vertical part."""


class Text(ObjectBase):
    type: Literal["text"] = "text"
    text: str = Field(min_length=1)
    at: Point
    anchor: Anchor = "center"
    size: Size | None = None
    color: ColorRef | None = None
    weight: Literal["regular", "bold"] | None = None
    italic: bool | None = None


class Math(ObjectBase):
    """A formula in TeX, set in display style and placed like a text.

    ``tex`` is what goes between the dollars: ``"\\frac{a}{b}"``. The
    front-end typesets it before anything is drawn, so a TeX mistake is
    reported (E-TEX) with this object's path.
    """

    type: Literal["math"] = "math"
    tex: str = Field(min_length=1)
    at: Point
    anchor: Anchor = "center"
    size: Size | None = None
    color: ColorRef | None = None


class Group(ObjectBase):
    """Objects that move together.

    ``children`` are ids of other objects. The transform scales and rotates
    them about ``pivot`` (degrees, counterclockwise), then translates them.
    The group's opacity multiplies each child's.
    """

    type: Literal["group"] = "group"
    children: tuple[Id, ...] = Field(min_length=1)
    translate: Point = (0, 0)
    rotate: Number = 0
    scale: PositiveNumber | tuple[PositiveNumber, PositiveNumber] = 1
    pivot: Point = (0, 0)


Shape = Circle | Ellipse | Rect | RegularPolygon | Polygon | Sector | Line | Polyline | Arc | Path
"""Every object that is drawn as a path."""

IRObject = Annotated[Shape | Text | Math | Group, Field(discriminator="type")]
"""Any core object; ``type`` picks the model."""
