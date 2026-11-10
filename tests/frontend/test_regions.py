"""Regions, flood fills and clips through the pipeline: the analysis's Figure 2 and more.

The four uses of Figure 2 are written as the analysis writes them (defs A,
B, outer and inner, and a flood fill bounded by a parabola, a line and a
wall), and their areas are checked against the exact values.
"""

import math
from collections.abc import Callable
from typing import Any

import pytest

from irpipe.artifacts import IR_SOURCE
from irpipe.core import Issue, Pipeline, RunResult
from irpipe.frontend.geometry import areas
from irpipe.frontend.measure import measure
from irpipe.frontend.normalize import normalize
from irpipe.frontend.place import place
from irpipe.frontend.resolve import Resolver
from irpipe.frontend.validate import Validate
from irpipe.metrics.fixed import FixedMetrics
from irpipe.schema import lir
from irpipe.schema.ir import IRDocument, Path

type Make = Callable[..., IRDocument]

DEFS: list[dict[str, Any]] = [
    {"id": "A", "type": "circle", "center": [-0.6, 0], "radius": 1.5},
    {"id": "B", "type": "circle", "center": [0.6, 0], "radius": 1.5},
    {"id": "outer", "type": "circle", "center": [0, -3], "radius": 1.2},
    {"id": "inner", "type": "circle", "center": [0, -3], "radius": 0.7},
]
# The parabola y = (x - 1)^2 / 2 from x = -1 to 3, as one quadratic Bezier.
F: dict[str, Any] = {"id": "f", "type": "path",
     "subpaths": [{"start": [-1, 2], "segments": [{"quad": [[1, -2], [3, 2]]}]}]}  # fmt: skip
G: dict[str, Any] = {"id": "g", "type": "line", "start": [-1, 1.5], "end": [3, 1.5]}
WALL: dict[str, Any] = {"id": "wall", "type": "line", "start": [2.5, -1], "end": [2.5, 3]}
FIGURE_2: list[dict[str, Any]] = [
    {"id": "A_only", "type": "region", "shape": {"difference": ["A", "B"]}, "fill": "a"},
    {"id": "AB", "type": "region", "shape": {"intersection": ["A", "B"]}, "fill": "b"},
    {"id": "ring", "type": "region", "shape": {"difference": ["outer", "inner"]}, "fill": "a"},
    F,
    G,
    WALL,
    {"id": "between_fg", "type": "flood_fill", "seed": [1.2, 0.4],
     "bounded_by": ["f", "g", "wall"], "fill": "b", "opacity": 0.3},
]  # fmt: skip

LENS = 2 * 1.5**2 * math.acos(0.4) - 0.6 * math.sqrt(9 - 1.44)
"""The area two circles of radius 1.5, 1.2 apart, share."""


def run_place(document: IRDocument) -> tuple[IRDocument | None, list[Issue]]:
    normal = normalize(document)
    measured, _ = measure(normal, FixedMetrics())
    assert measured is not None
    return place(normal, measured)


def placed(document: IRDocument) -> IRDocument:
    result, problems = run_place(document)
    assert result is not None, problems
    return result


def find(document: IRDocument, oid: str) -> Any:
    return next(obj for obj in (*document.objects, *document.defs) if obj.id == oid)


def area_of(document: IRDocument, oid: str) -> float:
    path = find(document, oid)
    assert isinstance(path, Path)
    rings = [lir.Subpath.model_validate(s.model_dump()) for s in path.subpaths]
    return float(areas.area(rings, path.fill_rule).area)


def drawn(document: IRDocument, oid: str) -> tuple[Any, ...]:
    normal = normalize(document)
    measured, _ = measure(normal, FixedMetrics())
    assert measured is not None
    out = Resolver(placed(document), measured).resolve()
    group = next(g for g in lir.walk_groups(out.items) if g.id == oid)
    return group.children


# Figure 2


def test_figure_2_difference_intersection_ring_and_flood_fill(document: Make) -> None:
    doc = placed(document(FIGURE_2, defs=DEFS))
    circle = math.pi * 1.5**2
    assert area_of(doc, "A_only") == pytest.approx(circle - LENS, rel=1e-3)
    assert area_of(doc, "AB") == pytest.approx(LENS, rel=1e-3)
    assert area_of(doc, "ring") == pytest.approx(math.pi * (1.2**2 - 0.7**2), rel=1e-3)
    assert len(find(doc, "ring").subpaths) == 2  # the outline and the hole
    root = math.sqrt(3)  # the parabola meets y = 1.5 at x = 1 - sqrt(3)
    under_line = (1.5 * 1.5 - 1.5**3 / 6) - (-1.5 * root + root**3 / 6)
    assert area_of(doc, "between_fg") == pytest.approx(under_line, rel=1e-3)


def test_regions_are_paths_drawn_even_odd_with_their_paint(document: Make) -> None:
    doc = placed(document(FIGURE_2, defs=DEFS))
    ring = find(doc, "ring")
    assert (ring.fill_rule, ring.fill, ring.color) == ("evenodd", "#FFD43B", "none")
    (item,) = drawn(document(FIGURE_2, defs=DEFS), "ring")
    assert item.fill.rule == "evenodd" and item.stroke is None and item.hint is None


def test_a_region_has_anchors_and_may_be_an_operand(document: Make) -> None:
    objects = [
        *FIGURE_2[:2],
        {"id": "both", "type": "region", "shape": {"union": ["A_only", "AB"]}, "fill": "a"},
        {"id": "t", "type": "text", "text": "x", "at": "AB.center"},
    ]
    doc = placed(document(objects, defs=DEFS))
    assert area_of(doc, "both") == pytest.approx(math.pi * 1.5**2, rel=1e-3)
    assert find(doc, "t").at == pytest.approx((0, 0), abs=1e-6)


def test_half_planes_and_xor(document: Make) -> None:
    left = {"half_plane": [[0, -5], [0, 5]]}  # left of an upward line: x < 0
    objects = [
        {"id": "west", "type": "region", "shape": {"intersection": ["A", left]}},
        {"id": "either", "type": "region", "shape": {"xor": ["A", "B"]}},
    ]
    doc = placed(document(objects, defs=DEFS))
    sliver = 1.5**2 * math.acos(0.4) - 0.6 * math.sqrt(1.5**2 - 0.36)  # A right of x = 0
    assert area_of(doc, "west") == pytest.approx(math.pi * 1.5**2 - sliver, rel=1e-3)
    assert area_of(doc, "either") == pytest.approx(2 * (math.pi * 1.5**2 - LENS), rel=1e-3)


def test_areas_under_and_between_graphs(document: Make) -> None:
    rising = {"id": "r", "type": "polyline", "points": [[-1, -1], [3, 3]]}
    flat = {"id": "h", "type": "line", "start": [-1, 3], "end": [3, 3]}
    objects = [
        rising,
        flat,
        {"id": "u", "type": "region", "shape": {"under": "r", "x": [0, 2]}},
        {"id": "w", "type": "region", "shape": {"between": ["h", "r"], "x": [0, 2]}},
    ]
    doc = placed(document(objects))
    assert area_of(doc, "u") == pytest.approx(2)
    assert area_of(doc, "w") == pytest.approx(4)


def test_a_graph_in_a_space_reads_x_and_y_0_there(document: Make) -> None:
    rising = {"id": "r", "type": "polyline", "in": "P", "points": [[0, 0], [2, 2]]}
    region = {"id": "u", "type": "region", "in": "P", "shape": {"under": "r", "x": [0, 2]},
              "fill": "a"}  # fmt: skip
    spaces = [{"id": "P", "origin": [1, 1], "unit": 2}]
    (item,) = drawn(document([rising, region], spaces=spaces), "u")
    assert item.stroke is None  # a region is not outlined unless it gives a color
    assert areas.area(item.subpaths).area == pytest.approx(8)  # 2 in P is 8 in the frame


# Problems


def test_an_operand_must_have_an_inside(document: Make, ir_text: Callable[..., str]) -> None:
    objects = [G, {"id": "r", "type": "region", "shape": {"difference": ["A", "g"]}}]
    result = Pipeline([Validate()], inputs=[IR_SOURCE]).run(
        {IR_SOURCE: ir_text(objects, defs=DEFS)}
    )
    (issue,) = result.issues
    assert (issue.code, issue.path, issue.message) == (
        "E-REGION",
        "objects[1].shape.difference[1]",
        "'g' is a line and has no inside",
    )


def validated(ir_text: Callable[..., str], objects: list[Any], **body: Any) -> RunResult:
    return Pipeline([Validate()], inputs=[IR_SOURCE]).run({IR_SOURCE: ir_text(objects, **body)})


def test_unknown_operands_and_wrong_boundaries(ir_text: Callable[..., str]) -> None:
    result = validated(ir_text, [{"id": "r", "type": "region", "shape": {"union": ["A", "Q"]}}],
                       defs=DEFS)  # fmt: skip
    (issue,) = result.issues
    assert (issue.code, issue.path) == ("E-REF", "objects[0].shape.union[1]")
    text = {"id": "t", "type": "text", "text": "x", "at": [0, 0]}
    fill = {"id": "ff", "type": "flood_fill", "seed": [0, 0], "bounded_by": ["t"]}
    (issue,) = validated(ir_text, [text, fill]).issues
    assert (issue.code, issue.path) == ("E-REGION", "objects[1].bounded_by[0]")


def test_a_seed_on_a_boundary_and_an_open_part_of_the_plane(document: Make) -> None:
    on_line = {**FIGURE_2[6], "seed": [1, 1.5]}
    _, problems = run_place(document([F, G, WALL, on_line]))
    (issue,) = problems
    assert (issue.code, issue.path) == ("E-REGION", "objects[3].seed")
    assert issue.message == "the seed of 'between_fg' lies on the line of 'g'"

    open_fill = {**FIGURE_2[6], "bounded_by": ["f", "g"], "seed": [1.2, 5]}
    _, problems = run_place(document([F, G, open_fill]))
    assert [p.message for p in problems] == [
        "the lines around the seed of 'between_fg' leave its part of the plane open"
    ]


def test_a_graph_that_does_not_reach_an_x(document: Make) -> None:
    region = {"id": "u", "type": "region", "shape": {"under": "g", "x": [0, 9]}}
    _, problems = run_place(document([G, region]))
    (issue,) = problems
    assert (issue.code, issue.path) == ("E-REGION", "objects[1].shape.under")
    assert issue.message == "'g' does not run from x = 0 to x = 9"


def test_an_empty_region_is_a_warning(document: Make) -> None:
    far = {"id": "far", "type": "circle", "center": [9, 0], "radius": 1}
    region = {"id": "none_", "type": "region", "shape": {"intersection": ["A", "far"]}}
    result, problems = run_place(document([region], defs=[*DEFS, far]))
    assert result is not None
    assert [(p.code, p.path) for p in problems] == [("W-EMPTY-REGION", "objects[0]")]
    assert drawn(document([region], defs=[*DEFS, far]), "none_") == ()


def test_a_region_that_uses_itself_is_a_loop(document: Make) -> None:
    region = {"id": "r", "type": "region", "shape": {"union": ["A", "r"]}}
    _, problems = run_place(document([region], defs=DEFS))
    assert [p.code for p in problems] == ["E-CYCLE"]


# Clips


LINE_ACROSS: dict[str, Any] = {
    "id": "l",
    "type": "line",
    "start": [-4, 0],
    "end": [4, 0],
    "color": "a",
}


def test_a_clip_cuts_lines_where_the_area_ends(document: Make) -> None:
    (item,) = drawn(document([{**LINE_ACROSS, "clip": "A"}], defs=DEFS), "l")
    (piece,) = item.subpaths
    assert piece.start == pytest.approx((-2.1, 0), abs=1e-3)
    assert piece.segments[-1].line == pytest.approx((0.9, 0), abs=1e-3)
    assert item.hint is None


def test_a_shape_wholly_inside_its_clip_is_drawn_as_it_is(document: Make) -> None:
    dot = {"id": "d", "type": "circle", "center": [-0.6, 0], "radius": 0.2, "clip": "A"}
    (item,) = drawn(document([dot], defs=DEFS), "d")
    assert item.hint == lir.CircleHint(center=(-0.6, 0), radius=0.2)


def test_a_group_clips_its_children_through_its_transform(document: Make) -> None:
    group = {"id": "g", "type": "group", "children": ["l"], "translate": [1, 0], "clip": "A"}
    (child,) = drawn(document([LINE_ACROSS, group], defs=DEFS), "g")
    (item,) = child.children
    (piece,) = item.subpaths
    # The clip is A in the frame; the line is drawn 1 to the right, so it is cut 1 to the left.
    assert piece.start == pytest.approx((-3.1, 0), abs=1e-3)
    assert piece.segments[-1].line == pytest.approx((-0.1, 0), abs=1e-3)


def test_clip_out_keeps_what_lies_outside(document: Make) -> None:
    (item,) = drawn(document([{**LINE_ACROSS, "clip_out": "A"}], defs=DEFS), "l")
    starts = sorted(piece.start[0] for piece in item.subpaths)
    assert starts == pytest.approx([-4, 0.9], abs=1e-3)


def test_a_clip_may_be_an_expression_and_becomes_a_def(document: Make) -> None:
    clipped = {**LINE_ACROSS, "clip": {"intersection": ["A", "B"]}}
    doc = placed(document([clipped], defs=DEFS))
    assert find(doc, "l").clip == "l.clip"
    assert area_of(doc, "l.clip") == pytest.approx(LENS, rel=1e-3)


def test_a_clipped_text_is_drawn_whole_with_a_warning(document: Make) -> None:
    text = {"id": "t", "type": "text", "text": "x", "at": [0, 0]}
    group = {"id": "g", "type": "group", "children": ["t"], "clip": "A"}
    result, problems = run_place(document([text, group], defs=DEFS))
    assert result is not None
    (issue,) = problems
    assert (issue.code, issue.path, issue.objects) == ("W-CLIP-TEXT", "objects[0]", ("t", "g"))
