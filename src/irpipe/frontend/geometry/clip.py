"""Clipping: what of a shape lies inside a mask, cut geometrically.

A shape is drawn with a fill and a stroke, and each is cut on its own: the
fill is the shape's area intersected with the mask, the stroke is its line
intersected with the mask (so a cut line ends where the mask's edge is,
with a flat end). Only what is cut changes: a shape wholly inside the mask
keeps its curves, and one wholly outside is gone.
"""

from collections.abc import Sequence

from shapely.geometry.base import BaseGeometry

from irpipe.frontend.geometry import areas
from irpipe.frontend.geometry.areas import FillRule
from irpipe.schema import lir


def clip_fill(
    subpaths: Sequence[lir.Subpath], rule: FillRule, mask: BaseGeometry
) -> tuple[tuple[lir.Subpath, ...], FillRule]:
    """The part of the subpaths' area inside ``mask``, and the fill rule to draw it with."""
    inside = areas.area(subpaths, rule)
    if mask.covers(inside):
        return tuple(subpaths), rule
    return areas.subpaths(inside.intersection(mask)), "evenodd"


def clip_stroke(subpaths: Sequence[lir.Subpath], mask: BaseGeometry) -> tuple[lir.Subpath, ...]:
    """The parts of the subpaths' lines inside ``mask``."""
    lines = areas.lines(subpaths)
    if mask.covers(lines):
        return tuple(subpaths)
    return areas.subpaths(lines.intersection(mask))
