"""Flood fill: the part of the plane the boundary lines enclose around a seed.

Like a paint bucket. The boundaries are lines, open or closed (a parabola,
a line and an axis will do); where they cross they cut the plane into
faces, and the face the seed lies in is the answer. Lines that run on past
a crossing do not matter. Faces may have holes: a closed line inside the
seed's face leaves its inside unpainted.
"""

from collections.abc import Sequence
from typing import Final

import shapely
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize

from irpipe.frontend.geometry.affine import XY

ON_LINE: Final = 1e-6
"""How close to a boundary, in units, the seed may come before it counts as on it."""


class FloodError(Exception):
    """The seed is on a boundary (``on``: its index), or its part of the plane is not closed."""

    def __init__(self, message: str, on: int | None = None) -> None:
        super().__init__(message)
        self.on = on


def flood(boundaries: Sequence[BaseGeometry], seed: XY) -> BaseGeometry:
    """The face of the plane, cut by ``boundaries``, that holds ``seed``."""
    probe = Point(seed)
    for k, line in enumerate(boundaries):
        if line.distance(probe) < ON_LINE:
            raise FloodError("the seed lies on a boundary", on=k)
    lines = shapely.union_all(list(boundaries))  # cut every line where another crosses it
    for face in polygonize(getattr(lines, "geoms", [lines])):
        if face.contains(probe):
            return face
    raise FloodError("the boundaries do not close the part of the plane the seed is in")
