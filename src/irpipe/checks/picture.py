"""The drawn picture as checks see it: every primitive in the frame, with its owner.

Checks run on what is actually drawn, the LIR, not on a simulation of it
(analysis §6). ``Picture`` flattens the LIR once: every path, text and
formula, its group transforms applied, in drawing order, as shapely
geometry in frame units, and tagged with the IR object that drew it. It
also keeps what checks need from the IR: the frame, the safe area, the
subtitle band, and which objects are related on purpose.

Related on purpose (analysis §5): one is placed by a reference to the
other (``"v.tip"``, ``{"on": ...}``, ``next_to``), one is built from the
other (a region's operands, a flood fill's lines, a clip), or both sit in
the same group or stack. Contact and overlap between related objects are
meant; readability is checked all the same.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from functools import cached_property
from itertools import combinations

import shapely
from shapely.geometry import Point, Polygon
from shapely.geometry.base import BaseGeometry

from irpipe import colormath
from irpipe.canvas import units
from irpipe.frontend.anchors import references, split_ref
from irpipe.frontend.geometry import affine, areas, curves
from irpipe.frontend.geometry.affine import Box, Matrix
from irpipe.frontend.references import body_objects
from irpipe.frontend.regions import operands
from irpipe.schema import lir
from irpipe.schema.ir import Container, FloodFill, IRDocument, Region

type Item = lir.PathItem | lir.TextItem | lir.MathItem


@dataclass(frozen=True)
class Drawn:
    """One primitive as drawn: where it lands in the frame, and which object drew it."""

    owner: str
    """The IR object it belongs to (its innermost LIR group)."""
    order: int
    """Its place in drawing order; a larger number is drawn on top."""
    item: Item
    fill: BaseGeometry | None
    """The filled area in the frame; for a text or formula, its box."""
    line: BaseGeometry | None
    """The stroked lines in the frame."""
    reach: Box
    """How far it reaches, half the stroke width included."""

    @property
    def is_text(self) -> bool:
        return isinstance(self.item, lir.TextItem | lir.MathItem)

    @cached_property
    def ink(self) -> BaseGeometry:
        """Everything it covers: its fill (or box) and its lines at their width."""
        parts = [self.fill] if self.fill is not None else []
        if self.line is not None and isinstance(self.item, lir.PathItem) and self.item.stroke:
            parts.append(self.line.buffer(units(self.item.stroke.width) / 2))
        return shapely.union_all(parts) if parts else areas.EMPTY


class Picture:
    """A LIR and the IR it came from, ready for checks."""

    def __init__(self, drawing: lir.LIRDocument, document: IRDocument) -> None:
        self.lir = drawing
        self.document = document
        width, height = drawing.canvas.units
        self.frame: Box = (-width / 2, -height / 2, width / 2, height / 2)
        self.safe: Box = document.frame.safe
        self.band: Box | None = document.frame.subtitle.band
        self.background: str = drawing.canvas.background
        self._sources: dict[str, str] = {}
        walked = list(self._walk(drawing.items, affine.IDENTITY))
        self.drawn: list[Drawn] = [
            _drawn(order, owner, item, to_frame)
            for order, (owner, item, to_frame) in enumerate(walked)
        ]

    @property
    def texts(self) -> list[Drawn]:
        return [d for d in self.drawn if d.is_text]

    def path(self, owner: str) -> str | None:
        """The JSON path, in the agent's file, of the object ``owner``."""
        return self._sources.get(owner)

    def related(self, first: str, second: str) -> bool:
        return frozenset((first, second)) in self._related

    def by_owner(self) -> dict[str, list[Drawn]]:
        """Every object's primitives, objects in drawing order."""
        found: dict[str, list[Drawn]] = {}
        for drawn in self.drawn:
            found.setdefault(drawn.owner, []).append(drawn)
        return found

    def color_at(self, x: float, y: float, before: int) -> colormath.RGB:
        """The color seen at (x, y) under everything drawn from ``before`` on.

        The background, with every fill drawn earlier that covers the point
        laid over it at its opacity, in drawing order.
        """
        seen = colormath.rgb(self.background)
        probe = Point(x, y)
        for drawn in self.drawn[:before]:
            item = drawn.item
            if (
                isinstance(item, lir.PathItem)
                and item.fill is not None
                and drawn.fill is not None
                and drawn.fill.contains(probe)
            ):
                seen = colormath.blend(colormath.rgb(item.fill.color), seen, item.fill.opacity)
        return seen

    def descendants(self, oid: str) -> list[str]:
        """The objects inside a group or stack, all the way down."""
        objects = {obj.id: obj for obj in self.document.objects}
        found: list[str] = []
        container = objects.get(oid)
        if isinstance(container, Container):
            for child in container.children:
                found.append(child)
                found += self.descendants(child)
        return found

    @cached_property
    def _related(self) -> frozenset[frozenset[str]]:
        return frozenset(_relations(self.document))

    def _walk(
        self, nodes: tuple[lir.Node, ...], to_frame: Matrix
    ) -> Iterator[tuple[str, Item, Matrix]]:
        """Every primitive in drawing order, with its owner and its map to the frame."""
        for node in nodes:
            if not isinstance(node, lir.Group):
                continue
            if node.source is not None:
                self._sources.setdefault(node.id, node.source)
            inner = affine.compose(to_frame, node.transform)
            for child in node.children:
                if isinstance(child, lir.Group):
                    yield from self._walk((child,), inner)
                elif isinstance(child, lir.PathItem | lir.TextItem | lir.MathItem):
                    yield node.id, child, inner


def _drawn(order: int, owner: str, item: Item, to_frame: Matrix) -> Drawn:
    if isinstance(item, lir.PathItem):
        subpaths = curves.transform(item.subpaths, to_frame)
        fill = areas.area(subpaths, item.fill.rule) if item.fill is not None else None
        line = areas.lines(subpaths) if item.stroke is not None else None
        half = units(item.stroke.width) / 2 if item.stroke is not None else 0.0
        x0, y0, x1, y1 = curves.bbox(subpaths)
        return Drawn(owner, order, item, fill, line, (x0 - half, y0 - half, x1 + half, y1 + half))
    x0, y0, x1, y1 = item.box
    corners = [affine.apply(to_frame, p) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    return Drawn(owner, order, item, Polygon(corners), None, affine.bounds(corners))


def beyond(reach: Box, box: Box, tolerance: float = 1e-3) -> list[tuple[str, float]]:
    """How far ``reach`` goes past each edge of ``box``: [("right", 0.4), ...]."""
    x0, y0, x1, y1 = reach
    left, bottom, right, top = box
    past = [("left", left - x0), ("right", x1 - right), ("bottom", bottom - y0), ("top", y1 - top)]
    return [(side, amount) for side, amount in past if amount > tolerance]


def reach_of(drawn: list[Drawn]) -> Box:
    """The box around several primitives' reach."""
    return affine.union(d.reach for d in drawn)


def _relations(document: IRDocument) -> Iterator[frozenset[str]]:
    """Every pair of objects related on purpose (see the module's docstring)."""
    for _, obj in body_objects(document):
        for _, ref in references(obj):
            target = split_ref(ref)[0] if isinstance(ref, str) else ref.on
            yield frozenset((obj.id, target))
        next_to = getattr(obj, "next_to", None)
        if next_to is not None:
            yield frozenset((obj.id, next_to))
        shapes = [getattr(obj, name) for name in ("clip", "clip_out")]
        if isinstance(obj, Region):
            shapes.append(obj.shape)
        for shape in shapes:
            if shape is not None:
                for _, target, _ in operands(shape, ""):
                    yield frozenset((obj.id, target))
        if isinstance(obj, FloodFill):
            for line in obj.bounded_by:
                yield frozenset((obj.id, line))
        if isinstance(obj, Container):
            for child in obj.children:
                yield frozenset((obj.id, child))
            for first, second in combinations(obj.children, 2):
                yield frozenset((first, second))
