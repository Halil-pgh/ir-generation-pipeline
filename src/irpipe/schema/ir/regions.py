"""Region expressions: areas built from shapes with set operations (analysis §2.6).

A region is written as an expression whose operands are areas:

    "A"                                   the inside of shape (or region) A
    {"union": ["A", "B"]}                 in A or in B
    {"intersection": ["A", "B"]}          in both
    {"difference": ["A", "B", "C"]}       in A but in neither B nor C
    {"xor": ["A", "B"]}                   in exactly one of the two
    {"half_plane": [p, q]}                left of the line from p to q
    {"under": "f", "x": [0, 2]}           between graph f and y = 0, for x from 0 to 2
    {"between": ["f", "g"], "x": [0, 2]}  between graphs f and g, for x from 0 to 2

Expressions nest: ``{"difference": [{"union": ["A", "B"]}, "C"]}``. A graph's
``x`` and ``y = 0`` are in the graph's own coordinates (its space, if it
has one). The front-end computes every region as geometry; backends get a
path, with holes where the region has them.
"""

from typing import Self

from pydantic import Field, model_validator

from irpipe.schema.base import StrictModel
from irpipe.schema.ir.common import Id, Number, Point


def _rising(x: tuple[float, float]) -> tuple[float, float]:
    if x[0] >= x[1]:
        raise ValueError(f"x runs from the smaller value to the larger; got [{x[0]:g}, {x[1]:g}]")
    return x


class UnionOf(StrictModel):
    union: tuple["RegionShape", ...] = Field(min_length=2)


class IntersectionOf(StrictModel):
    intersection: tuple["RegionShape", ...] = Field(min_length=2)


class DifferenceOf(StrictModel):
    """The first area without the others."""

    difference: tuple["RegionShape", ...] = Field(min_length=2)


class XorOf(StrictModel):
    """Where exactly one of the two areas is."""

    xor: tuple["RegionShape", "RegionShape"]


class HalfPlane(StrictModel):
    """Everything to the left of the line through two points, going from the first to the second."""

    half_plane: tuple[Point, Point]


class Under(StrictModel):
    """Between a graph and the line y = 0 of its own coordinates, from ``x[0]`` to ``x[1]``."""

    under: Id
    x: tuple[Number, Number]

    @model_validator(mode="after")
    def _x_rises(self) -> Self:
        _rising(self.x)
        return self


class Between(StrictModel):
    """Between two graphs, from ``x[0]`` to ``x[1]`` (in the first graph's coordinates)."""

    between: tuple[Id, Id]
    x: tuple[Number, Number]

    @model_validator(mode="after")
    def _x_rises(self) -> Self:
        _rising(self.x)
        return self


RegionShape = Id | UnionOf | IntersectionOf | DifferenceOf | XorOf | HalfPlane | Under | Between
"""An area: an object's id, or an expression over areas."""

Operation = UnionOf | IntersectionOf | DifferenceOf | XorOf

for _model in (UnionOf, IntersectionOf, DifferenceOf, XorOf):
    _model.model_rebuild()


def parts(shape: RegionShape) -> tuple[RegionShape, ...]:
    """The areas a set operation combines; nothing for the other forms."""
    match shape:
        case UnionOf(union=found) | IntersectionOf(intersection=found):
            return found
        case DifferenceOf(difference=found) | XorOf(xor=found):
            return found
    return ()
