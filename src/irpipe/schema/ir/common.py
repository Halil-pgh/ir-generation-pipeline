"""Small types the IR's header and body share: ids, points, boxes and sizes.

Positions and lengths are in units of the frame (short side 9, origin at the
center, y up). Type sizes, stroke widths and dashes are in reference pixels
(short side 1080), as in the render profile.

A ``Number`` of geometry may be written as an expression (irpipe/expr):
``"44/17"``, ``"sqrt(2)/2"``, ``"k*b_x"``. It is computed while the IR is
validated, so every model holds plain floats. Names come from the IR's
``values`` table, handed in as the validation context ``{"values": ...}``.
"""

from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, Field, PositiveFloat, ValidationInfo
from pydantic_core import PydanticCustomError

from irpipe.expr import ExprError, evaluate
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

Point = tuple[Number, Number]
Box = tuple[float, float, float, float]
"""Left, bottom, right, top, in units."""

Role = Literal["title", "heading", "body", "label", "caption"]
Size = Role | PositiveFloat
"""A text role from the header's type scale, or a size in reference pixels."""
