"""Small types the IR's header and body share: ids, points, boxes, sizes and directions.

Positions and lengths are in units of the frame (short side 9, origin at the
center, y up), or of the object's space when it names one with ``in``. Type
sizes, stroke widths and dashes are in reference pixels (short side 1080), as
in the render profile.

A ``Number`` of geometry may be written as an expression (irpipe/expr):
``"44/17"``, ``"sqrt(2)/2"``, ``"k*b_x"``. It is computed while the IR is
validated, so every model holds plain floats. Names come from the IR's
``values`` table, handed in as the validation context ``{"values": ...}``.

A ``Point`` is two numbers, or a reference to a point the front-end works
out (analysis §2.3): ``"v.tip"`` names an anchor of another object, and
``{"on": "f", "t": 0.5}`` or ``{"on": "f", "x": 2}`` a point on its outline.
The place stage turns every reference into numbers.
"""

from typing import Annotated, Any, Literal, Self

from pydantic import (
    AfterValidator,
    BeforeValidator,
    Field,
    PositiveFloat,
    ValidationInfo,
    model_validator,
)
from pydantic_core import PydanticCustomError

from irpipe.expr import ExprError, evaluate
from irpipe.schema.base import StrictModel
from irpipe.schema.color import NAME_PATTERN

Id = Annotated[str, Field(pattern=NAME_PATTERN)]
"""An object id: a letter, then letters, digits or ``_``. Dots are kept for parts (``v.label``)."""

Name = Id
"""The name of a style, zone or space in the header or body."""


def _compute(value: Any, info: ValidationInfo) -> Any:
    """An expression becomes its value; anything else is left to the float check."""
    if not isinstance(value, str):
        return value
    values = (info.context or {}).get("values", {})
    try:
        return float(evaluate(value, values))
    except ExprError as error:
        raise PydanticCustomError(
            "expression", "{message}", {"message": str(error), "hint": error.hint or ""}
        ) from None


Number = Annotated[float, BeforeValidator(_compute, json_schema_input_type=float | str)]
"""A number of geometry, or an expression that computes it."""

PositiveNumber = Annotated[Number, Field(gt=0)]
NonNegativeNumber = Annotated[Number, Field(ge=0)]

XY = tuple[Number, Number]
"""Two numbers: a point, or a shift such as a group's ``translate``."""

AnchorRef = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")]
"""``"<id>.<anchor>"``: a named point of an object (``"v.tip"``), a zone, ``frame`` or ``safe``."""


class OnRef(StrictModel):
    """A point on an object's outline: ``t`` of the way along it, or where it reaches ``x``.

    ``t`` runs from 0 at the start to 1 at the end, by length. ``x`` is in the
    object's own coordinates (its space, if it has one); the first point in
    drawing order that reaches it is taken.
    """

    on: Id
    t: float | None = Field(default=None, ge=0, le=1)
    x: Number | None = None

    @model_validator(mode="after")
    def _one_way(self) -> Self:
        if (self.t is None) == (self.x is None):
            raise ValueError("a point on an outline gives either t or x")
        return self


Point = XY | AnchorRef | OnRef
"""``[x, y]``, ``"id.anchor"``, or ``{"on": id, "t": ...}`` / ``{"on": id, "x": ...}``."""

Box = tuple[float, float, float, float]
"""Left, bottom, right, top, in units."""

Role = Literal["title", "heading", "body", "label", "caption"]
Size = Role | PositiveFloat
"""A text role from the header's type scale, or a size in reference pixels."""


def _not_zero(vector: tuple[float, float]) -> tuple[float, float]:
    if vector == (0, 0):
        raise ValueError("[0, 0] points nowhere; give a direction with some length")
    return vector


DirectionName = Literal[
    "up", "down", "left", "right", "up_left", "up_right", "down_left", "down_right"
]
Direction = DirectionName | float | Annotated[tuple[float, float], AfterValidator(_not_zero)]
"""Which way: a name, an angle in degrees (counterclockwise from +x), or ``[dx, dy]``."""

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
"""A point of a box: horizontal part, then vertical part; ``center`` alone is both."""
