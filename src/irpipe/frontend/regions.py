"""Regions, flood fills and clips: areas worked out from the IR's shapes (analysis §2.6).

The place stage builds every area here, in the frame, and writes it back
as a path (with holes where it has them); backends only ever see paths.

    E-REGION        an area cannot be built: an operand with no inside, a
                    seed on a boundary or in a part of the plane the
                    boundaries leave open, a graph that does not reach an x
    W-EMPTY-REGION  a region or flood fill came out empty, so nothing is drawn
    W-CLIP-TEXT     a text or formula is clipped; it is drawn whole

What may be an operand: any closed shape (circle, ellipse, rect, regular
polygon, polygon, sector, path) and any region or flood fill. Lines,
polylines and arcs have no inside; they can be graphs (``under``,
``between``) and boundaries of a flood fill.
"""

from collections.abc import Sequence
from typing import Final, Protocol

import shapely
from shapely.geometry.base import BaseGeometry

from irpipe.core import ISSUE_CODES, IssueCode, Origin
from irpipe.frontend.geometry import affine, areas
from irpipe.frontend.geometry.affine import XY, Box, Matrix
from irpipe.schema.ir import (
    Arc,
    Area,
    Between,
    DifferenceOf,
    HalfPlane,
    IntersectionOf,
    Line,
    Point,
    Polyline,
    RegionShape,
    Shape,
    Under,
    UnionOf,
    XorOf,
)
from irpipe.schema.ir.objects import ObjectBase

E_REGION = ISSUE_CODES.register(
    IssueCode(
        "E-REGION",
        Origin.IR,
        "an area cannot be built: an operand with no inside, a seed on a line or in an "
        "open part of the plane, or a graph that does not reach an x",
    )
)
W_EMPTY_REGION = ISSUE_CODES.register(
    IssueCode(
        "W-EMPTY-REGION",
        Origin.IR,
        "a region or flood fill came out empty, so nothing is drawn",
        allowable=True,
    )
)
W_CLIP_TEXT = ISSUE_CODES.register(
    IssueCode(
        "W-CLIP-TEXT",
        Origin.IR,
        "a text or formula is clipped; texts and formulas are drawn whole",
        allowable=True,
    )
)

OPEN: Final = (Line, Polyline, Arc)


def has_inside(obj: ObjectBase) -> bool:
    """Can ``obj`` be an operand of a region (or a clip)?"""
    return isinstance(obj, Shape | Area) and not isinstance(obj, OPEN)


def can_bound(obj: ObjectBase) -> bool:
    """Can ``obj`` be a boundary of a flood fill or a graph of a region?"""
    return isinstance(obj, Shape | Area)


def operands(shape: RegionShape, path: str) -> list[tuple[str, str, str]]:
    """Every id an expression names, as (path, id, role); role is "area" or "graph"."""
    found: list[tuple[str, str, str]] = []
    match shape:
        case str(oid):
            found.append((path, oid, "area"))
        case UnionOf(union=parts) | IntersectionOf(intersection=parts):
            key = "union" if isinstance(shape, UnionOf) else "intersection"
            for k, part in enumerate(parts):
                found += operands(part, f"{path}.{key}[{k}]")
        case DifferenceOf(difference=parts) | XorOf(xor=parts):
            key = "difference" if isinstance(shape, DifferenceOf) else "xor"
            for k, part in enumerate(parts):
                found += operands(part, f"{path}.{key}[{k}]")
        case Under(under=graph):
            found.append((f"{path}.under", graph, "graph"))
        case Between(between=graphs):
            found += [(f"{path}.between[{k}]", graph, "graph") for k, graph in enumerate(graphs)]
    return found


class RegionError(Exception):
    def __init__(self, message: str, path: str, objects: Sequence[str], hint: str) -> None:
        super().__init__(message)
        self.issue = E_REGION(message, path=path, objects=list(objects), hint=hint)


class Source(Protocol):
    """What the place stage gives region building: shapes and points, in the frame."""

    @property
    def frame(self) -> Box: ...

    def area(self, oid: str) -> BaseGeometry: ...

    def point(self, owner: str, point: Point, where: str) -> XY: ...

    def graph(self, oid: str, x0: float, x1: float) -> list[XY] | None: ...

    def own_to_frame(self, oid: str) -> Matrix: ...


def build(shape: RegionShape, source: Source, owner: str, where: str) -> BaseGeometry:
    """The area ``shape`` describes, in the frame; ``where`` is its JSON path."""
    match shape:
        case str(oid):
            return source.area(oid)
        case UnionOf(union=parts):
            return shapely.union_all(_each(parts, source, owner, f"{where}.union"))
        case IntersectionOf(intersection=parts):
            found = _each(parts, source, owner, f"{where}.intersection")
            result = found[0]
            for part in found[1:]:
                result = result.intersection(part)
            return result
        case DifferenceOf(difference=parts):
            first, *rest = _each(parts, source, owner, f"{where}.difference")
            return first.difference(shapely.union_all(rest))
        case XorOf(xor=parts):
            a, b = _each(parts, source, owner, f"{where}.xor")
            return a.symmetric_difference(b)
        case HalfPlane(half_plane=(p, q)):
            start = source.point(owner, p, f"{where}.half_plane[0]")
            end = source.point(owner, q, f"{where}.half_plane[1]")
            if start == end:
                raise RegionError(
                    "a half plane needs two different points",
                    f"{where}.half_plane",
                    [owner],
                    "the line runs from the first point to the second; the half plane is "
                    "on its left",
                )
            return areas.half_plane(start, end, source.frame)
        case Under(under=graph, x=(x0, x1)):
            points = _graph(source, graph, x0, x1, f"{where}.under")
            return areas.transform(areas.under(points), source.own_to_frame(graph))
        case Between(between=(upper, lower), x=(x0, x1)):
            graphs = [
                [
                    affine.apply(source.own_to_frame(g), p)
                    for p in _graph(source, g, x0, x1, f"{where}.between[{k}]")
                ]
                for k, g in enumerate((upper, lower))
            ]
            return areas.between(graphs[0], graphs[1])
    raise TypeError(f"unknown region expression {shape!r}")


def _each(
    parts: Sequence[RegionShape], source: Source, owner: str, where: str
) -> list[BaseGeometry]:
    return [build(part, source, owner, f"{where}[{k}]") for k, part in enumerate(parts)]


def _graph(source: Source, graph: str, x0: float, x1: float, where: str) -> list[XY]:
    points = source.graph(graph, x0, x1)
    if points is None:
        raise RegionError(
            f"'{graph}' does not run from x = {x0:g} to x = {x1:g}",
            where,
            [graph],
            "choose an x range the graph covers; x is in the graph's own coordinates",
        )
    return points
