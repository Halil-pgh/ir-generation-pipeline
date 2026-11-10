"""place: references, boxes beside things, stacks and spaces become plain numbers.

Texts are measured with the "fixed" measurer: a glyph is 0.55 of the size
wide, the box reaches 0.75 of the size above the baseline and 0.25 below,
and 120 reference px make one unit. A ``label`` text (38 px) of one glyph is
therefore 38 * 0.55 / 120 units wide and 38 / 120 tall.
"""

from collections.abc import Callable
from typing import Any

import pytest

from irpipe.artifacts import IR_NORMAL, IR_PLACED, MEASURED
from irpipe.core import Issue, Pipeline
from irpipe.frontend.measure import measure
from irpipe.frontend.normalize import normalize
from irpipe.frontend.place import Place, place
from irpipe.frontend.resolve import Resolver
from irpipe.metrics.fixed import FixedMetrics
from irpipe.schema import lir
from irpipe.schema.ir import Group, IRDocument, Text

type Make = Callable[..., IRDocument]

V = {"id": "v", "type": "line", "start": [0, 0], "end": [2, 1]}
C = {"id": "c", "type": "circle", "center": [0, 0], "radius": 1}
GLYPH = 38 * 0.55 / 120  # one label glyph's width in units
TALL = 38 / 120  # a label text's height in units


def text(oid: str, content: str = "x", **fields: Any) -> dict[str, Any]:
    return {"id": oid, "type": "text", "text": content, "size": "label", **fields}


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
    return next(obj for obj in document.objects if obj.id == oid)


def drawn_box(document: IRDocument, oid: str) -> lir.Box:
    """Where the text ``oid`` is drawn in the end, through resolve."""
    normal = normalize(document)
    measured, _ = measure(normal, FixedMetrics())
    assert measured is not None
    out = Resolver(placed(document), measured).resolve()
    group = next(g for g in lir.walk_groups(out.items) if g.id == oid)
    (item,) = group.children
    assert isinstance(item, lir.TextItem)
    return item.box


# References


def test_a_text_at_v_tip_sits_on_the_line_end_by_its_left_baseline(document: Make) -> None:
    doc = placed(document([V, text("t", at="v.tip", anchor="left_baseline")]))
    t = find(doc, "t")
    assert (t.at, t.anchor) == ((2, 1), "left_baseline")
    left, bottom, _, _ = drawn_box(
        document([V, text("t", at="v.tip", anchor="left_baseline")]), "t"
    )
    assert (left, bottom) == pytest.approx((2, 1 - 0.25 * TALL))


def test_a_reference_follows_the_object_it_names(document: Make) -> None:
    moved = {**V, "end": [3, -1]}
    t = find(placed(document([moved, text("t", at="v.tip")])), "t")
    assert t.at == (3, -1)


@pytest.mark.parametrize(
    ("ref", "point"),
    [
        ("v.start", (0, 0)),
        ("v.tail", (0, 0)),
        ("v.mid", (1, 0.5)),
        ("v.right_top", (2, 1)),
        ("c.center", (0, 0)),
        ("c.center_top", (0, 1)),
        ("frame.left_top", (-8, 4.5)),
        ("safe.center_bottom", (0, -4.1)),
        ("plot.right_center", (4, 1)),
    ],
)
def test_named_points_of_objects_zones_and_the_frame(
    document: Make, ref: str, point: tuple[float, float]
) -> None:
    doc = document([V, C, text("t", at=ref)], zones={"plot": [0, 0, 4, 2]})
    assert find(placed(doc), "t").at == pytest.approx(point)


def test_the_center_of_an_arc_is_its_circles_center_not_its_boxes(document: Make) -> None:
    arc = {"id": "a", "type": "arc", "center": [1, 1], "radius": 1, "start_angle": 0,
           "end_angle": 90}  # fmt: skip
    assert find(placed(document([arc, text("t", at="a.center")])), "t").at == (1, 1)


def test_points_on_an_outline_by_length_and_by_x(document: Make) -> None:
    graph = {"id": "f", "type": "polyline", "points": [[0, 0], [2, 2], [4, 0]]}
    objects = [
        graph,
        text("half", at={"on": "f", "t": 0.5}),
        text("at_three", at={"on": "f", "x": 3}),
    ]
    doc = placed(document(objects))
    assert find(doc, "half").at == pytest.approx((2, 2))
    assert find(doc, "at_three").at == pytest.approx((3, 1))


def test_an_x_the_outline_never_reaches_says_where_it_runs(document: Make) -> None:
    graph = {"id": "f", "type": "polyline", "points": [[0, 0], [4, 0]]}
    _, problems = run_place(document([graph, text("t", at={"on": "f", "x": 9})]))
    (issue,) = problems
    assert (issue.code, issue.path) == ("E-PLACE", "objects[1].at.x")
    assert issue.message == "'f' never reaches x = 9; it runs from x = 0 to 4"


def test_a_shape_can_be_drawn_between_two_references(document: Make) -> None:
    joint = {"id": "j", "type": "line", "start": "c.center_top", "end": "v.tip"}
    j = find(placed(document([V, C, joint])), "j")
    assert (j.start, j.end) == ((0, 1), (2, 1))


# Groups and spaces


def test_a_reference_lands_on_its_anchor_through_groups(document: Make) -> None:
    group = {"id": "g", "type": "group", "children": ["v"], "translate": [1, 0], "rotate": 90}
    objects = [V, group, text("out", at="v.tip"), text("dot", at=[0, 0])]
    doc = placed(document(objects))
    assert find(doc, "out").at == pytest.approx((0, 2))  # (2, 1) turned a quarter, then moved

    inner = {**text("inner", at="c.center"), "id": "inner"}
    group_in = {"id": "g", "type": "group", "children": ["inner"], "translate": [1, 0]}
    doc = placed(document([C, inner, group_in]))
    assert find(doc, "inner").at == pytest.approx((-1, 0))  # drawn at c's center, (0, 0)


def test_a_group_may_turn_about_a_referenced_point(document: Make) -> None:
    square = {"id": "s", "type": "rect", "center": [2, 0], "width": 1, "height": 1}
    group = {"id": "g", "type": "group", "children": ["s"], "rotate": 45, "pivot": "s.center"}
    g = find(placed(document([square, group])), "g")
    assert g.pivot == (2, 0)


def test_a_space_maps_its_numbers_and_references_read_the_frame(document: Make) -> None:
    dot = {"id": "c", "type": "circle", "in": "P", "center": [1, 0], "radius": 0.5}
    objects = [dot, text("t", at="c.center"), text("u", **{"in": "P"}, at="c.right_center")]
    doc = placed(document(objects, spaces=[{"id": "P", "origin": [1, 1], "unit": 2}]))
    assert find(doc, "t").at == (3, 1)
    assert find(doc, "u").at == pytest.approx((1.5, 0))  # (4, 1) in the frame, in P's numbers


def test_a_space_origin_may_be_a_reference(document: Make) -> None:
    space = {"id": "P", "origin": "safe.left_bottom", "unit": [1, 2]}
    doc = placed(document([C], spaces=[space]))
    assert doc.spaces[0].origin == (-7.6, -4.1)


# Beside a point, next to an object


def test_beside_a_point_the_box_keeps_the_gap(document: Make) -> None:
    t = find(placed(document([V, text("t", at="v.tip", dir="right", gap=0.5)])), "t")
    assert (t.at, t.anchor) == (pytest.approx((2 + 0.5 + GLYPH / 2, 1)), "center")


def test_next_to_puts_the_box_beside_the_other_box(document: Make) -> None:
    right = find(placed(document([C, text("t", next_to="c")])), "t")
    assert right.at == pytest.approx((1 + 0.2 + GLYPH / 2, 0))
    below = find(placed(document([C, text("t", next_to="c", dir="down", gap=0)])), "t")
    assert below.at == pytest.approx((0, -1 - TALL / 2))


# Stacks


def test_a_column_lines_its_children_up_and_becomes_a_group(document: Make) -> None:
    objects = [
        text("one", "x"),
        text("two", "xxx"),
        {"id": "s", "type": "stack", "children": ["one", "two"], "align": "left_center",
         "spacing": 0.5, "at": [0, 0], "anchor": "left_top"},
    ]  # fmt: skip
    doc = placed(document(objects))
    stack = find(doc, "s")
    assert isinstance(stack, Group)
    assert stack.children == ("one", "two")
    one, two = drawn_box(document(objects), "one"), drawn_box(document(objects), "two")
    assert one == pytest.approx((0, -TALL, GLYPH, 0))
    assert two == pytest.approx((0, -2 * TALL - 0.5, 3 * GLYPH, -TALL - 0.5))


def test_a_row_on_baselines_shares_one_baseline(document: Make) -> None:
    objects = [
        text("small", "x"),
        {**text("big", "x"), "size": "title"},
        {"id": "s", "type": "stack", "arrange": "row", "children": ["small", "big"],
         "align": "center_baseline", "at": [0, 0]},
        text("under", at="s.left_baseline", anchor="left_baseline"),
    ]  # fmt: skip
    doc = placed(document(objects))
    small, big = drawn_box(document(objects), "small"), drawn_box(document(objects), "big")
    baseline = small[1] + 0.25 * TALL
    assert big[1] + 0.25 * 64 / 120 == pytest.approx(baseline)
    assert find(doc, "under").at[1] == pytest.approx(baseline)


def test_a_grid_and_a_stack_inside_a_stack(document: Make) -> None:
    objects = [
        *(text(f"t{k}") for k in range(4)),
        {"id": "inner", "type": "stack", "arrange": "grid", "columns": 2,
         "children": ["t0", "t1", "t2", "t3"], "spacing": 0},
        text("head"),
        {"id": "outer", "type": "stack", "children": ["head", "inner"], "spacing": 0,
         "at": [0, 0], "anchor": "left_top", "align": "left_center"},
        text("probe", at="t3.left_bottom"),
    ]  # fmt: skip
    doc = placed(document(objects))
    assert find(doc, "inner").translate == pytest.approx((0, -TALL))  # below "head"
    assert find(doc, "probe").at == pytest.approx((GLYPH, -3 * TALL))  # second row, second column


# What has no place, and what goes round in a loop


def test_a_box_needs_a_place(document: Make) -> None:
    _, problems = run_place(document([text("t")]))
    (issue,) = problems
    assert (issue.code, issue.path, issue.message) == (
        "E-PLACE",
        "objects[0]",
        "text 't' has no place",
    )


def test_a_stack_child_does_not_place_itself(document: Make) -> None:
    stack = {"id": "s", "type": "stack", "children": ["t"], "at": [0, 0]}
    _, problems = run_place(document([text("t", at=[1, 1]), stack]))
    (issue,) = problems
    assert (issue.code, issue.path) == ("E-PLACE", "objects[0].at")


def test_positions_that_depend_on_each_other_are_a_loop(document: Make) -> None:
    objects = [text("a", at="b.center"), text("b", at="a.right_top")]
    _, problems = run_place(document(objects))
    (issue,) = problems
    assert (issue.code, issue.path) == ("E-CYCLE", "objects[0]")
    assert issue.message == "positions depend on each other in a loop: a -> b -> a"


def test_a_child_cannot_sit_on_its_own_group(document: Make) -> None:
    group = {"id": "g", "type": "group", "children": ["c", "t"]}
    _, problems = run_place(document([C, text("t", at="g.right_top"), group]))
    assert [p.code for p in problems] == ["E-CYCLE"]


# The stage


def test_the_stage_writes_the_placed_ir(document: Make) -> None:
    normal = normalize(document([V, text("t", at="v.tip")]))
    measured, _ = measure(normal, FixedMetrics())
    result = Pipeline([Place()], inputs=[IR_NORMAL, MEASURED]).run(
        {IR_NORMAL: normal, MEASURED: measured}
    )
    t = find(result.get(IR_PLACED), "t")
    assert isinstance(t, Text) and t.at == (2, 1)
