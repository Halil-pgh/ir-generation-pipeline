"""The drawable objects of IR 1.0's core: circle, rect, line, path, text, group.

    {"id": "c", "type": "circle", "center": [0, 0], "radius": 1.5, "color": "a"}

Every object has an ``id`` and a ``type``; the type selects the model. Paint
fields left out (``None``) are inherited: theme, then the style classes the
object names, then the object itself (docs/SEMANTICS.md). ``"none"`` as a
color means no paint at all.

This is the first subset. Expressions such as ``"44/17"`` (step 8), anchor
references such as ``"v.tip"``, coordinate spaces, labels, markers and math
(step 11) widen these types later.
"""

from typing import Annotated, Literal

from pydantic import Field, NonNegativeFloat, PositiveFloat

from irpipe.schema.base import StrictModel
from irpipe.schema.color import ColorRef
from irpipe.schema.ir.common import Id, Name, Point, Size

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
    radius: PositiveFloat


class Rect(Filled):
    """An axis-aligned rectangle; turn it with a group."""

    type: Literal["rect"] = "rect"
    center: Point
    width: PositiveFloat
    height: PositiveFloat
    corner_radius: NonNegativeFloat = 0


class Line(Stroked):
    type: Literal["line"] = "line"
    start: Point
    end: Point


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


class Group(ObjectBase):
    """Objects that move together.

    ``children`` are ids of other objects. The transform scales and rotates
    them about ``pivot`` (degrees, counterclockwise), then translates them.
    The group's opacity multiplies each child's.
    """

    type: Literal["group"] = "group"
    children: tuple[Id, ...] = Field(min_length=1)
    translate: Point = (0, 0)
    rotate: float = 0
    scale: PositiveFloat | tuple[PositiveFloat, PositiveFloat] = 1
    pivot: Point = (0, 0)


IRObject = Annotated[Circle | Rect | Line | Path | Text | Group, Field(discriminator="type")]
"""Any core object; ``type`` picks the model."""
