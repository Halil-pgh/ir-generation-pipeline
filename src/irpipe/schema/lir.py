"""LIR 1.0: the resolved draw list every backend draws (analysis §3).

The front-end turns an IR into LIR; a backend (SVG, Manim) only draws it.
Everything is already decided here: positions, colors, opacities, measured
text boxes and the drawing order. A backend never lays out, never resolves a
name and never reorders.

    {"version": "lir/1.0",
     "canvas": {"units": [16, 9], "pixels": [1920, 1080], "background": "#0E1117"},
     "items": [{"type": "group", "id": "a", "children": [{"type": "path", ...}]}]}

Every IR object becomes a group carrying its id, so lint findings, generated
code and later animation can name the object the agent wrote.

Positions are in units (short side 9, origin at the center, y up); stroke
widths, dashes and type sizes are in reference pixels (short side 1080).
Colors are always ``"#RRGGBB"``. LIR imports nothing from the IR schema, so
the IR can grow (expressions, references) without changing what backends read.
"""

from typing import Annotated, Final, Literal, Self

from pydantic import Field, NonNegativeFloat, PositiveFloat, PositiveInt, model_validator

from irpipe.schema.base import StrictModel
from irpipe.schema.color import HEX_PATTERN

LIR_VERSION: Final = "lir/1.0"

Hex = Annotated[str, Field(pattern=HEX_PATTERN)]
Opacity = Annotated[float, Field(ge=0, le=1)]
Point = tuple[float, float]
Box = tuple[float, float, float, float]
"""Left, bottom, right, top, in units."""

GroupId = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)*$")]
"""An IR object id, or a part of one (``axes.tick_3``) for pieces a component made."""

IDENTITY: Final = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


class LineTo(StrictModel):
    line: Point


class QuadTo(StrictModel):
    quad: tuple[Point, Point]


class CubicTo(StrictModel):
    cubic: tuple[Point, Point, Point]


Segment = LineTo | QuadTo | CubicTo


class Subpath(StrictModel):
    start: Point
    segments: tuple[Segment, ...] = Field(min_length=1)
    closed: bool = False


class FillPaint(StrictModel):
    color: Hex
    opacity: Opacity = 1
    rule: Literal["nonzero", "evenodd"] = "nonzero"


class StrokePaint(StrictModel):
    color: Hex
    opacity: Opacity = 1
    width: PositiveFloat
    dash: tuple[PositiveFloat, ...] | None = None
    cap: Literal["butt", "round", "square"] = "butt"
    join: Literal["miter", "round", "bevel"] = "miter"


class CircleHint(StrictModel):
    shape: Literal["circle"] = "circle"
    center: Point
    radius: PositiveFloat


class RectHint(StrictModel):
    shape: Literal["rect"] = "rect"
    center: Point
    width: PositiveFloat
    height: PositiveFloat
    corner_radius: NonNegativeFloat = 0


class LineHint(StrictModel):
    shape: Literal["line"] = "line"
    start: Point
    end: Point


ShapeHint = Annotated[CircleHint | RectHint | LineHint, Field(discriminator="shape")]


class Primitive(StrictModel):
    """Fields every primitive has; ``depth`` is for 3D (analysis §5)."""

    type: str
    depth: float | None = None


class PathItem(Primitive):
    """Straight and Bezier subpaths with an optional fill and stroke.

    ``hint`` lets a backend use its library's own class (Manim's ``Circle``);
    the geometry drawn must still be the one in ``subpaths``.
    """

    type: Literal["path"] = "path"
    subpaths: tuple[Subpath, ...] = Field(min_length=1)
    fill: FillPaint | None = None
    stroke: StrokePaint | None = None
    hint: ShapeHint | None = None

    @model_validator(mode="after")
    def _paints_something(self) -> Self:
        if self.fill is None and self.stroke is None:
            raise ValueError("a path needs a fill, a stroke or both")
        return self


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


class TextItem(Primitive):
    """A line of text, with the box and baseline the front-end measured."""

    type: Literal["text"] = "text"
    text: str = Field(min_length=1)
    font: str
    size: PositiveFloat
    weight: Literal["regular", "bold"] = "regular"
    italic: bool = False
    color: Hex
    opacity: Opacity = 1
    at: Point
    anchor: Anchor
    box: Box
    baseline: float


class MathItem(Primitive):
    """A formula; ``glyphs`` are its outlines, for backends that have no LaTeX."""

    type: Literal["math"] = "math"
    tex: str = Field(min_length=1)
    size: PositiveFloat
    color: Hex
    opacity: Opacity = 1
    at: Point
    anchor: Anchor
    box: Box
    baseline: float
    glyphs: tuple[Subpath, ...] = ()


class ImageItem(Primitive):
    """A raster image stretched over ``box``; SVG assets arrive as paths instead."""

    type: Literal["image"] = "image"
    src: str = Field(min_length=1)
    box: Box
    opacity: Opacity = 1


class Group(StrictModel):
    """One IR object (or a part of one) and the primitives it was drawn with.

    ``transform`` is an affine matrix ``[a, b, c, d, e, f]``: a point (x, y)
    goes to (a x + c y + e, b x + d y + f). ``source`` is the object's JSON path
    in the IR. Children are already in drawing order: each group's ``z`` is at
    least the one before it.
    """

    type: Literal["group"] = "group"
    id: GroupId
    source: str | None = None
    transform: tuple[float, float, float, float, float, float] = IDENTITY
    z: float = 0
    depth: float | None = None
    children: tuple["Node", ...] = ()

    @model_validator(mode="after")
    def _children_in_drawing_order(self) -> Self:
        _check_order(self.children, where=f"group '{self.id}'")
        return self


Node = Annotated[PathItem | TextItem | MathItem | ImageItem | Group, Field(discriminator="type")]
Group.model_rebuild()


class LIRCanvas(StrictModel):
    """The frame: units per side, output pixels and the background."""

    units: tuple[PositiveFloat, PositiveFloat]
    pixels: tuple[PositiveInt, PositiveInt]
    background: Hex


class LIRDocument(StrictModel):
    """A whole ``lir.json``: one group per drawn IR object, in drawing order."""

    version: Literal["lir/1.0"] = LIR_VERSION
    canvas: LIRCanvas
    items: tuple[Group, ...] = ()

    @model_validator(mode="after")
    def _ids_unique_and_ordered(self) -> Self:
        _check_order(self.items, where="items")
        seen: set[str] = set()
        for group in walk_groups(self.items):
            if group.id in seen:
                raise ValueError(f"group id '{group.id}' appears twice")
            seen.add(group.id)
        return self


def walk_groups(nodes: tuple[object, ...]) -> list[Group]:
    """Every group in ``nodes`` and below, parents before children."""
    found: list[Group] = []
    for node in nodes:
        if isinstance(node, Group):
            found.append(node)
            found.extend(walk_groups(node.children))
    return found


def _check_order(nodes: tuple[object, ...], *, where: str) -> None:
    previous: Group | None = None
    for node in nodes:
        if not isinstance(node, Group):
            continue
        if previous is not None and node.z < previous.z:
            raise ValueError(
                f"{where}: group '{node.id}' (z={node.z}) comes after '{previous.id}' "
                f"(z={previous.z}); the front-end must sort by z"
            )
        previous = node
