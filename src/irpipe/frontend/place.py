"""Stage "place": every position worked out, so that resolve only has to draw (analysis §2.3).

    requires  ir_normal   the normalized IR (labels are objects by now)
              measured    every text's and formula's box
    provides  ir_placed   the same IR with every position as numbers

What it works out:

- references: ``"v.tip"`` and ``{"on": ...}`` become numbers in the
  coordinates of the object that holds them (its space and its groups
  undone), so the point lands exactly on that anchor in the picture;
- boxes: a text, formula or stack given ``at`` + ``dir`` or ``next_to``
  gets the ``at`` and ``anchor`` that put it there;
- stacks: each child is moved into its cell, and the stack becomes a plain
  group of its children;
- spaces: an ``origin`` given by reference becomes numbers. Objects keep
  their ``in``; resolve maps their points.

Positions are worked out when first needed, so objects may refer to ones
written later. Positions that depend on each other in a loop are E-CYCLE.

    E-PLACE   a text, formula or stack has no place (no at, no next_to, not
              in a stack), a stack's child gives a place of its own, or an
              ``{"on": ..., "x": ...}`` point lies beyond the outline
    E-CYCLE   positions depend on each other in a loop
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, Final

from irpipe.artifacts import IR_NORMAL, IR_PLACED, MEASURED
from irpipe.canvas import units
from irpipe.core import ISSUE_CODES, STAGES, Issue, IssueCode, Origin, Stage, StageContext
from irpipe.frontend import layout, shapes
from irpipe.frontend.anchors import SAME_AS, Centered, map_points, split_ref, xy
from irpipe.frontend.expressions import E_CYCLE
from irpipe.frontend.geometry import affine, curves
from irpipe.frontend.geometry.affine import XY, Box, Matrix
from irpipe.frontend.labels import source_paths
from irpipe.metrics import TextBox
from irpipe.schema import lir
from irpipe.schema.ir import (
    Container,
    Group,
    IRDocument,
    Math,
    OnRef,
    Placed,
    Point,
    Shape,
    Stack,
    Text,
)
from irpipe.schema.ir.objects import ObjectBase

E_PLACE = ISSUE_CODES.register(
    IssueCode(
        "E-PLACE",
        Origin.IR,
        "an object has no place, two places, or a point that is not on its outline",
    )
)

GAP: Final = 0.2
"""Units between a box and the point or object it sits beside, when ``gap`` is left out."""


class PlaceError(Exception):
    def __init__(self, issue: Issue) -> None:
        super().__init__(issue.message)
        self.issue = issue


@STAGES.register
class Place(Stage):
    name = "place"
    requires = (IR_NORMAL, MEASURED)
    provides = (IR_PLACED,)

    def run(self, ctx: StageContext) -> None:
        measured = ctx.read(MEASURED)
        placed, problems = place(ctx.read(IR_NORMAL), measured)
        ctx.report(*problems)
        if placed is not None:
            ctx.write(IR_PLACED, placed)


def place(
    document: IRDocument, measured: dict[str, TextBox]
) -> tuple[IRDocument | None, list[Issue]]:
    """The placed document, or None and the problems that stopped it."""
    problems = list(missing_places(document))
    if problems:
        return None, problems
    try:
        return Placer(document, measured).placed(), []
    except PlaceError as error:
        return None, [error.issue]


def missing_places(document: IRDocument) -> Iterator[Issue]:
    """An E-PLACE for every box with no place, and every stack child with a place of its own."""
    stack_of = {
        child: obj.id
        for obj in document.objects
        if isinstance(obj, Stack)
        for child in obj.children
    }
    paths = source_paths(document)
    for obj in (*document.defs, *document.objects):
        if not isinstance(obj, Placed):
            continue
        given = [name for name in ("at", "next_to") if getattr(obj, name) is not None]
        if obj.id in stack_of and given:
            yield E_PLACE(
                f"'{obj.id}' is in stack '{stack_of[obj.id]}', which places it, "
                f"but it also gives {given[0]}",
                path=f"{paths[obj.id]}.{given[0]}",
                objects=[obj.id, stack_of[obj.id]],
                hint="leave at and next_to out, or take it out of the stack",
            )
        elif obj.id not in stack_of and not given:
            yield E_PLACE(
                f"{obj.type} '{obj.id}' has no place",
                path=paths[obj.id],
                objects=[obj.id],
                hint='give "at" (a point or a reference such as "v.tip"), or "next_to", '
                "or put it in a stack",
            )


@dataclass(frozen=True)
class StackPlacement:
    box: Box
    baseline: float
    offsets: dict[str, XY]
    """How far each child moves, in the stack's coordinates."""


class Placer:
    """Works out the positions of one normalized, measured document.

    Coordinates, from an object outward: its own (the numbers it holds, in
    its space if it has one) -> drawing coordinates (after the space; those of
    its group's content, or the frame at the top) -> the frame (after the
    stack moves it and every group around it). A reference names a point of
    the frame.
    """

    def __init__(self, document: IRDocument, measured: dict[str, TextBox]) -> None:
        self._document = document
        self._measured = measured
        self._objects: dict[str, ObjectBase] = {
            obj.id: obj for obj in (*document.defs, *document.objects)
        }
        self._paths = source_paths(document) | {
            space.id: f"spaces[{k}]" for k, space in enumerate(document.spaces)
        }
        self._parent = {
            child: obj.id
            for obj in document.objects
            if isinstance(obj, Container)
            for child in obj.children
        }
        self._spaces = {space.id: space for space in document.spaces}
        width, height = document.frame.units
        self._boxes: dict[str, Box] = {
            "frame": (-width / 2, -height / 2, width / 2, height / 2),
            "safe": document.frame.safe,
            **document.zones,
        }
        self._done: dict[tuple[str, str], Any] = {}
        self._active: list[tuple[str, str]] = []

    def placed(self) -> IRDocument:
        """The document with every position as numbers and every stack a group."""
        spaces = tuple(
            space.model_copy(update={"origin": self._origin(space.id)})
            for space in self._document.spaces
        )
        return self._document.model_copy(
            update={
                "objects": tuple(self._final(obj.id) for obj in self._document.objects),
                "defs": tuple(self._final(obj.id) for obj in self._document.defs),
                "spaces": spaces,
            }
        )

    # -- what is written out ------------------------------------------------

    def _final(self, oid: str) -> ObjectBase:
        """The object as written out: its own numbers, moved where its stack put it."""
        local = self._local(oid)
        dx, dy = self._offset(oid)
        if isinstance(local, Stack):
            return Group.model_construct(
                id=local.id,
                children=local.children,
                opacity=local.opacity,
                z=local.z,
                tags=local.tags,
                covers=local.covers,
                translate=(dx, dy),
            )
        if (dx, dy) == (0, 0):
            return local
        if isinstance(local, Group):
            tx, ty = local.translate
            return local.model_copy(update={"translate": (tx + dx, ty + dy)})
        ux, uy = self._space_units(local)
        return map_points(local, lambda p, _: (xy(p)[0] + dx / ux, xy(p)[1] + dy / uy))

    # -- an object's own numbers -------------------------------------------

    def _local(self, oid: str) -> ObjectBase:
        """The object with its points as numbers in its own coordinates, before a stack moves it."""
        return self._once("local", oid, lambda: self._compute_local(oid))

    def _compute_local(self, oid: str) -> ObjectBase:
        obj = self._objects[oid]
        to_draw = self._space(obj)
        path = self._paths[oid]

        def numbers(point: Point, where: str) -> XY:
            if isinstance(point, tuple):
                return xy(point)
            target = point.on if isinstance(point, OnRef) else split_ref(point)[0]
            if isinstance(obj, Group) and self._inside(target, oid):
                # A group's pivot is in its content's coordinates: a point of its own
                # content is read there, before the group turns it.
                return self._frame_point(point, f"{path}.{where}", within=oid)
            back = affine.invert(affine.compose(self._parent_to_frame(oid), to_draw))
            return affine.apply(back, self._frame_point(point, f"{path}.{where}"))

        local = map_points(obj, numbers)
        if isinstance(local, Text | Math):
            width, ascent, descent = self._size(oid)
            at, anchor = self._box_place(local, width, ascent, descent)
            if at is not None:
                at = affine.apply(affine.invert(to_draw), at)
            local = local.model_copy(
                update={
                    "at": at or (0.0, 0.0),
                    "anchor": anchor,
                    "dir": None,
                    "gap": None,
                    "next_to": None,
                }
            )
        return local

    def _box_place(
        self, box: Placed, width: float, ascent: float, descent: float
    ) -> tuple[XY | None, str]:
        """Where a box goes, in drawing coordinates: a point and the anchor that sits on it.

        ``box`` holds its ``at`` as numbers in its own coordinates. The
        point is None for a box in a stack, which the stack moves. Beside a
        point or an object, the point is the box's center (``center`` is the
        middle from descent to ascent, so it is the box's middle too).
        """
        if box.next_to is not None:
            target = self._box_in(box.id, box.next_to)
            u = layout.unit_vector(box.dir or "right")
            gap = GAP if box.gap is None else box.gap
            return layout.beside(target, u, gap, width, ascent + descent), "center"
        if box.at is None:
            return None, "center"
        at = affine.apply(self._space(box), xy(box.at))
        if box.dir is not None:
            u = layout.unit_vector(box.dir)
            gap = GAP if box.gap is None else box.gap
            return layout.beside((*at, *at), u, gap, width, ascent + descent), "center"
        return at, box.anchor or "center"

    def _size(self, oid: str) -> tuple[float, float, float]:
        box = self._measured[oid]
        return units(box.width), units(box.ascent), units(box.descent)

    # -- coordinates --------------------------------------------------------

    def _space(self, obj: ObjectBase) -> Matrix:
        """Own coordinates -> drawing coordinates."""
        name = getattr(obj, "space", None)
        if name is None:
            return affine.IDENTITY
        ox, oy = self._origin(name)
        ux, uy = self._spaces[name].units
        return (ux, 0.0, 0.0, uy, ox, oy)

    def _space_units(self, obj: ObjectBase) -> XY:
        name = getattr(obj, "space", None)
        return (1.0, 1.0) if name is None else self._spaces[name].units

    def _origin(self, name: str) -> XY:
        def compute() -> XY:
            space = self._spaces[name]
            if isinstance(space.origin, tuple):
                return xy(space.origin)
            return self._frame_point(space.origin, f"{self._paths[name]}.origin")

        return self._once("origin", name, compute)

    def _to_frame(self, oid: str, within: str | None = None) -> Matrix:
        """Drawing coordinates -> the frame, with the move a stack gives the object.

        ``within`` names a group around the object: the map then stops at
        that group's content, before the group's own transform.
        """
        return self._once(
            f"to_frame@{within}",
            oid,
            lambda: affine.compose(
                self._parent_to_frame(oid, within), affine.translation(*self._offset(oid))
            ),
        )

    def _parent_to_frame(self, oid: str, within: str | None = None) -> Matrix:
        parent = self._parent.get(oid)
        if parent is None or parent == within:
            return affine.IDENTITY
        container = self._local(parent)
        if isinstance(container, Group):
            return affine.compose(self._to_frame(parent, within), shapes.group_matrix(container))
        return self._to_frame(parent, within)

    def _inside(self, oid: str, container: str) -> bool:
        """Is ``oid`` somewhere inside ``container``?"""
        parent = self._parent.get(oid)
        while parent is not None:
            if parent == container:
                return True
            parent = self._parent.get(parent)
        return False

    def _offset(self, oid: str) -> XY:
        parent = self._parent.get(oid)
        if parent is None or not isinstance(self._objects[parent], Stack):
            return (0.0, 0.0)
        return self._stack(parent).offsets[oid]

    # -- points the IR can name ---------------------------------------------

    def _frame_point(self, ref: str | OnRef, where: str, within: str | None = None) -> XY:
        """The point a reference names, in the frame (or in the content of group ``within``)."""
        if isinstance(ref, OnRef):
            return self._point_on(ref, where, within)
        target, name = split_ref(ref)
        if target in self._boxes:
            return layout.box_point(self._boxes[target], name)
        return self._anchor(target, SAME_AS.get(name, name), within)

    def _anchor(self, oid: str, name: str, within: str | None = None) -> XY:
        obj = self._objects[oid]
        to_frame = self._to_frame(oid, within)
        local = self._local(oid)
        if name == "center" and isinstance(local, Centered):
            center = affine.apply(self._space(obj), xy(local.center))
            return affine.apply(to_frame, center)
        if name in ("start", "end", "mid"):
            subpaths = self._outline(oid)
            if name == "start":
                at = subpaths[0].start
            elif name == "end":
                at = curves.end_point(subpaths)
            else:
                at, _ = curves.point_at(subpaths, 0.5)
            return affine.apply(to_frame, at)
        box, baseline = self._draw_box(oid)
        return affine.apply(to_frame, layout.box_point(box, name, baseline))

    def _point_on(self, ref: OnRef, where: str, within: str | None = None) -> XY:
        oid = ref.on
        if ref.t is not None:
            at, _ = curves.point_at(self._outline(oid), ref.t)
            return affine.apply(self._to_frame(oid, within), at)
        assert ref.x is not None
        local = self._local(oid)
        assert isinstance(local, Shape)
        own, _, _ = shapes.outline(local)
        found = curves.crossing(own, ref.x)
        if found is None:
            low, _, high, _ = curves.bbox(own)
            raise PlaceError(
                E_PLACE(
                    f"'{oid}' never reaches x = {ref.x:g}; it runs from x = {low:g} to {high:g}",
                    path=f"{where}.x",
                    objects=[oid],
                    hint="choose an x inside that range",
                )
            )
        drawn = affine.apply(self._space(local), found)
        return affine.apply(self._to_frame(oid, within), drawn)

    # -- shapes and boxes in drawing coordinates ----------------------------

    def _outline(self, oid: str) -> tuple[lir.Subpath, ...]:
        def compute() -> tuple[lir.Subpath, ...]:
            local = self._local(oid)
            assert isinstance(local, Shape)
            subpaths, _, _ = shapes.outline(local)
            return curves.transform(subpaths, self._space(local))

        return self._once("outline", oid, compute)

    def _draw_box(self, oid: str) -> tuple[Box, float]:
        """The object's box and baseline in its drawing coordinates, before a stack moves it.

        A shape's box is its geometry's (strokes are not counted) and its
        baseline its bottom; a group's box surrounds its children's boxes.
        """
        return self._once("box", oid, lambda: self._compute_box(oid))

    def _compute_box(self, oid: str) -> tuple[Box, float]:
        local = self._local(oid)
        if isinstance(local, Text | Math):
            width, ascent, descent = self._size(oid)
            at = affine.apply(self._space(local), xy(local.at or (0.0, 0.0)))
            return layout.box_at(at, local.anchor or "center", width, ascent, descent)
        if isinstance(local, Stack):
            placement = self._stack(oid)
            return placement.box, placement.baseline
        if isinstance(local, Group):
            matrix = shapes.group_matrix(local)
            box = affine.union(
                affine.transform_box(matrix, self._draw_box(child)[0]) for child in local.children
            )
            return box, box[1]
        box = curves.bbox(self._outline(oid))
        return box, box[1]

    def _box_in(self, oid: str, target: str) -> Box:
        """``target``'s box in the drawing coordinates of ``oid``."""
        if target in self._boxes:
            frame_box = self._boxes[target]
        else:
            frame_box = affine.transform_box(self._to_frame(target), self._draw_box(target)[0])
        return affine.transform_box(affine.invert(self._parent_to_frame(oid)), frame_box)

    def _stack(self, sid: str) -> StackPlacement:
        return self._once("stack", sid, lambda: self._compute_stack(sid))

    def _compute_stack(self, sid: str) -> StackPlacement:
        stack = self._local(sid)
        assert isinstance(stack, Stack)
        boxes = [self._draw_box(child) for child in stack.children]
        sizes = [(x1 - x0, y1 - base, base - y0) for (x0, y0, x1, y1), base in boxes]
        columns = {"column": 1, "row": len(boxes), "grid": stack.columns or 1}[stack.arrange]
        spacing = stack.spacing
        if not isinstance(spacing, tuple):
            spacing = (spacing, spacing)
        on_baselines = layout.anchor_parts(stack.align)[1] == "baseline"
        cells = layout.grid(sizes, columns, spacing, on_baselines=on_baselines)
        moves: list[XY] = []
        for (box, base), cell, cell_base in zip(boxes, cells.cells, cells.baselines, strict=True):
            to = layout.box_point(cell, stack.align, cell_base)
            start = layout.box_point(box, stack.align, base)
            moves.append((to[0] - start[0], to[1] - start[1]))
        first_baseline = boxes[0][1] + moves[0][1]
        _, bottom, width, _ = cells.box
        ascent, descent = -first_baseline, first_baseline - bottom
        at, anchor = self._box_place(stack, width, ascent, descent)
        if at is None:
            box, baseline = cells.box, first_baseline
        else:
            box, baseline = layout.box_at(at, anchor, width, ascent, descent)
        shift = (box[0], box[3])  # the grid was laid out with its left-top corner at (0, 0)
        offsets = {
            child: (mx + shift[0], my + shift[1])
            for child, (mx, my) in zip(stack.children, moves, strict=True)
        }
        return StackPlacement(box=box, baseline=baseline, offsets=offsets)

    # -- working out once, and loops ----------------------------------------

    def _once[T](self, kind: str, oid: str, compute: Callable[[], T]) -> T:
        key = (kind, oid)
        if key in self._done:
            return self._done[key]  # type: ignore[no-any-return]
        if key in self._active:
            self._loop(key)
        self._active.append(key)
        try:
            value = compute()
        finally:
            self._active.pop()
        self._done[key] = value
        return value

    def _loop(self, key: tuple[str, str]) -> None:
        ids = list(dict.fromkeys(oid for _, oid in self._active[self._active.index(key) :]))
        raise PlaceError(
            E_CYCLE(
                "positions depend on each other in a loop: " + " -> ".join([*ids, ids[0]]),
                path=self._paths.get(ids[0]),
                objects=[oid for oid in ids if oid in self._objects],
                hint="place one of them with numbers, or by something outside the loop",
            )
        )
