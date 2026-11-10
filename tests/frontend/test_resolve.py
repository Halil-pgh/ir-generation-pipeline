"""resolve: a placed IR becomes LIR, one group per object.

The tests write IRs the way an agent would and normalize, measure and place
them first, as the pipeline does; the cascade is tested in test_paint and
test_normalize, positions in test_place.
"""

from collections.abc import Callable
from typing import Any

import pytest

from irpipe.artifacts import IR_PLACED, LIR, MEASURED
from irpipe.core import Pipeline
from irpipe.frontend.layout import box_at
from irpipe.frontend.measure import measure
from irpipe.frontend.normalize import normalize
from irpipe.frontend.place import place
from irpipe.frontend.resolve import Resolve, Resolver
from irpipe.metrics import MathBox, TextBox
from irpipe.metrics.fixed import FixedMetrics
from irpipe.metrics.svgpath import Subpath
from irpipe.schema import lir
from irpipe.schema.ir import IRDocument

CIRCLE = {"id": "c", "type": "circle", "center": [1, 2], "radius": 0.5, "fill": "a"}
LINE = {"id": "l", "type": "line", "start": [0, 0], "end": [2, 1], "color": "b"}

type Make = Callable[..., IRDocument]


def placed(document: IRDocument, measured: dict[str, TextBox] | None = None) -> IRDocument:
    normal = normalize(document)
    if measured is None:
        measured, _ = measure(normal, FixedMetrics())
        assert measured is not None
    result, problems = place(normal, measured)
    assert result is not None, problems
    return result


def resolve(document: IRDocument) -> lir.LIRDocument:
    normal = normalize(document)
    measured, _ = measure(normal, FixedMetrics())
    assert measured is not None
    return Resolver(placed(document), measured).resolve()


def first_item(group: lir.Group) -> Any:
    (item,) = group.children
    return item


def subgroup(group: lir.Group, index: int) -> lir.Group:
    child = group.children[index]
    assert isinstance(child, lir.Group)
    return child


def test_every_object_becomes_a_group_with_its_id_and_source(document: Make) -> None:
    out = resolve(document([CIRCLE, LINE]))
    assert [(g.id, g.source) for g in out.items] == [("c", "objects[0]"), ("l", "objects[1]")]
    assert out.canvas.units == (16, 9)
    assert out.canvas.background == "#0E1117"


def test_grouped_objects_are_drawn_inside_their_group_at_its_place(document: Make) -> None:
    objects = [CIRCLE, {**LINE, "id": "m"}, {"id": "g", "type": "group", "children": ["m", "c"]}]
    out = resolve(document(objects))
    (group,) = out.items
    assert group.id == "g"
    assert [child.id for child in lir.walk_groups(group.children)] == ["m", "c"]


def test_siblings_are_sorted_by_z_and_ties_keep_list_order(document: Make) -> None:
    objects = [{**CIRCLE, "z": 2}, LINE, {**LINE, "id": "m"}, {**CIRCLE, "id": "d", "z": -1}]
    assert [g.id for g in resolve(document(objects)).items] == ["d", "l", "m", "c"]


# Shapes and paint


def test_a_circle_is_a_closed_bezier_path_with_a_hint(document: Make) -> None:
    item = first_item(resolve(document([CIRCLE])).items[0])
    assert isinstance(item, lir.PathItem)
    (subpath,) = item.subpaths
    assert subpath.closed and len(subpath.segments) == 4
    assert item.hint == lir.CircleHint(center=(1, 2), radius=0.5)
    assert item.fill is not None and item.fill.color == "#FFD43B"
    assert item.stroke is not None and item.stroke.color == "#FFFFFF"  # theme on a dark frame


def test_a_line_never_gets_a_fill(document: Make) -> None:
    item = first_item(resolve(document([{**LINE, "style": "boxed"}])).items[0])
    assert item.fill is None
    assert item.stroke.color == "#58C4DD"  # b, the line's own color


@pytest.mark.parametrize(
    "shape",
    [
        {"id": "z", "type": "polyline", "points": [[0, 0], [1, 1], [2, 0]]},
        {
            "id": "z",
            "type": "arc",
            "center": [0, 0],
            "radius": 1,
            "start_angle": 0,
            "end_angle": 90,
        },
    ],
)
def test_open_shapes_are_never_filled_even_by_a_class(
    document: Make, shape: dict[str, Any]
) -> None:
    item = first_item(resolve(document([{**shape, "style": "boxed"}])).items[0])
    assert item.fill is None
    assert item.stroke.color == "#58C4DD"  # the class's line color still applies


@pytest.mark.parametrize(
    ("shape", "hint"),
    [
        ({"type": "ellipse", "center": [0, 0], "rx": 2, "ry": 1}, lir.EllipseHint),
        (
            {"type": "regular_polygon", "center": [0, 0], "radius": 1, "sides": 6},
            lir.RegularPolygonHint,
        ),
        ({"type": "polygon", "points": [[0, 0], [1, 0], [0, 1]]}, lir.PolygonHint),
        (
            {"type": "sector", "center": [0, 0], "radius": 1, "start_angle": 0, "end_angle": 60},
            lir.SectorHint,
        ),
    ],
)
def test_closed_shapes_become_filled_paths_with_their_hint(
    document: Make, shape: dict[str, Any], hint: type
) -> None:
    item = first_item(resolve(document([{"id": "s", **shape, "fill": "a"}])).items[0])
    assert isinstance(item.hint, hint)
    assert item.fill.color == "#FFD43B"
    assert item.subpaths[0].closed


def test_the_object_wins_over_its_classes_and_the_classes_over_the_theme(document: Make) -> None:
    line = {**LINE, "style": ["dashed", "boxed"], "color": "a"}
    stroke = first_item(resolve(document([line])).items[0]).stroke
    assert stroke.color == "#FFD43B"  # object
    assert (stroke.width, stroke.dash) == (3, (14, 10))  # class "dashed"


def test_opacity_multiplies_down_through_groups(document: Make) -> None:
    objects = [
        {**CIRCLE, "opacity": 0.5, "fill_opacity": 0.5},
        {"id": "g", "type": "group", "children": ["c"], "style": "muted"},
    ]
    item = first_item(subgroup(resolve(document(objects)).items[0], 0))
    assert item.stroke.opacity == pytest.approx(0.25)  # group 0.5 x circle 0.5
    assert item.fill.opacity == pytest.approx(0.125)  # and x fill_opacity 0.5


def test_an_object_that_paints_nothing_keeps_an_empty_group(document: Make) -> None:
    out = resolve(document([{**CIRCLE, "fill": "none", "color": "none"}]))
    assert out.items[0].children == ()


def test_a_rectangle_is_closed_and_rounds_its_corners_with_arcs(document: Make) -> None:
    rect = {"id": "r", "type": "rect", "center": [0, 0], "width": 4, "height": 2}
    sharp = first_item(resolve(document([rect])).items[0])
    round_ = first_item(resolve(document([{**rect, "corner_radius": 0.5}])).items[0])
    assert len(sharp.subpaths[0].segments) == 3  # the fourth side is the closing edge
    assert sharp.subpaths[0].closed
    assert len(round_.subpaths[0].segments) == 8


def test_a_path_keeps_its_segments_and_fill_rule(document: Make) -> None:
    path = {
        "id": "p",
        "type": "path",
        "fill": "a",
        "fill_rule": "evenodd",
        "subpaths": [{"start": [0, 0], "segments": [{"line": [1, 0]}, {"line": [0, 1]}]}],
    }
    item = first_item(resolve(document([path])).items[0])
    assert item.fill.rule == "evenodd"
    assert item.subpaths[0].segments[1] == lir.LineTo(line=(0, 1))


def test_a_group_carries_its_transform(document: Make) -> None:
    objects = [CIRCLE, {"id": "g", "type": "group", "children": ["c"], "translate": [1, 2]}]
    assert resolve(document(objects)).items[0].transform == (1, 0, 0, 1, 1, 2)


def test_defs_are_not_drawn(document: Make) -> None:
    out = resolve(document([LINE], defs=[CIRCLE]))
    assert [g.id for g in out.items] == ["l"]


# Text


def test_a_text_is_measured_and_placed_by_its_anchor(document: Make) -> None:
    text = {"id": "t", "type": "text", "text": "ab", "at": [1, 1], "anchor": "left_baseline"}
    item = first_item(resolve(document([{**text, "size": "label"}])).items[0])
    assert isinstance(item, lir.TextItem)
    assert (item.font, item.size, item.baseline) == ("Inter", 38, 1)
    width = 2 * 38 * 0.55 / 120  # two glyphs of the fixed measurer, in units
    assert item.box == pytest.approx((1, 1 - 38 * 0.25 / 120, 1 + width, 1 + 38 * 0.75 / 120))


@pytest.mark.parametrize(
    ("anchor", "x0", "baseline"),
    [
        ("left_baseline", 0, 0),
        ("center", -1, -1),  # the box runs from -2 to 2, so the baseline is at -1
        ("right_top", -2, -3),
        ("center_bottom", -1, 1),
    ],
)
def test_the_anchor_point_sits_at_at(anchor: str, x0: float, baseline: float) -> None:
    (bx0, _, _, _), found = box_at((0, 0), anchor, 2, 3, 1)
    assert (bx0, found) == pytest.approx((x0, baseline))


def test_a_text_without_color_or_size_takes_the_theme_and_body(document: Make) -> None:
    item = first_item(
        resolve(document([{"id": "t", "type": "text", "text": "x", "at": [0, 0]}])).items[0]
    )
    assert (item.color, item.size) == ("#FFFFFF", 42)


# The stage


def test_the_stage_reads_the_placed_ir_and_writes_lir(document: Make) -> None:
    pipeline = Pipeline([Resolve()], inputs=[IR_PLACED, MEASURED])
    result = pipeline.run({IR_PLACED: placed(document([CIRCLE])), MEASURED: {}})
    assert isinstance(result.get(LIR), lir.LIRDocument)


def test_a_formula_carries_its_glyphs_placed_on_its_box(document: Make) -> None:
    formula = {"id": "f", "type": "math", "tex": "x", "at": [1, 2], "anchor": "left_baseline"}
    square = Subpath((0, 0), [("line", ((120, 0),)), ("line", ((120, 120),))], closed=True)
    measured: dict[str, TextBox] = {
        "f": MathBox(width=120, ascent=120, descent=0, outlines=(square,))
    }
    (group,) = Resolver(placed(document([formula]), measured), measured).resolve().items
    item = first_item(group)
    assert isinstance(item, lir.MathItem)
    assert item.box == pytest.approx((1, 2, 2, 3))  # 120 reference px is one unit
    (glyph,) = item.glyphs
    assert glyph.start == pytest.approx((1, 2))
    assert glyph.segments[1] == lir.LineTo(line=(2, 3))


def test_the_light_theme_draws_in_black(ir: Callable[..., dict[str, Any]]) -> None:
    data = ir([{key: value for key, value in LINE.items() if key != "color"}])
    data["frame"]["background"] = "#FAFAFA"
    item = first_item(resolve(IRDocument.model_validate(data)).items[0])
    assert item.stroke.color == "#000000"


# Arrowheads


def items(document: IRDocument, oid: str) -> tuple[Any, ...]:
    group = next(g for g in lir.walk_groups(resolve(document).items) if g.id == oid)
    return group.children


def test_an_arrow_is_a_head_at_the_tip_and_a_line_that_stops_inside_it(document: Make) -> None:
    vector = {**LINE, "end": [2, 0], "stroke_width": 4, "arrows": ["end"]}
    line, head = items(document([vector]), "l")
    length = (4 * 4 + 10) / 120  # 26 reference px
    assert head.fill.color == line.stroke.color == "#58C4DD"
    assert head.stroke is None
    (triangle,) = head.subpaths
    assert triangle.start == (2, 0)  # the tip is the line's end
    assert triangle.segments[0].line == pytest.approx((2 - length, 0.4 * length))
    assert line.subpaths[0].segments[-1].line == pytest.approx((2 - 0.6 * length, 0))
    assert line.hint == lir.LineHint(start=(0, 0), end=line.subpaths[0].segments[-1].line)


def test_arrows_at_the_start_and_midway_point_the_way_the_line_runs(document: Make) -> None:
    vector = {**LINE, "end": [2, 0], "arrows": ["start", "mid"], "arrow_size": 24}
    _, head = items(document([vector]), "l")
    start, middle = head.subpaths
    assert start.start == (0, 0)
    assert start.segments[0].line[0] == pytest.approx(0.2)  # the head points back, to -x
    assert middle.start == pytest.approx((1.1, 0))  # centered on the middle, pointing +x


def test_an_arc_with_an_arrow_goes_without_a_hint(document: Make) -> None:
    arc = {"id": "a", "type": "arc", "center": [0, 0], "radius": 1, "start_angle": 0,
           "end_angle": 90, "arrows": ["end"]}  # fmt: skip
    line, _ = items(document([arc]), "a")
    assert line.hint is None


def test_a_line_that_paints_nothing_has_no_arrow(document: Make) -> None:
    assert items(document([{**LINE, "color": "none", "arrows": ["end"]}]), "l") == ()


# Spaces


def test_a_space_maps_points_and_lengths_but_not_the_stroke(document: Make) -> None:
    circle = {**CIRCLE, "in": "P", "center": [1, 0], "stroke_width": 5}
    spaces = [{"id": "P", "origin": [1, 1], "unit": 2}]
    (path,) = items(document([circle], spaces=spaces), "c")
    assert path.hint == lir.CircleHint(center=(3, 1), radius=1)
    assert path.stroke.width == 5


def test_different_scales_make_a_circle_an_ellipse(document: Make) -> None:
    spaces = [{"id": "P", "unit": [2, 1]}]
    (path,) = items(document([{**CIRCLE, "in": "P"}], spaces=spaces), "c")
    assert path.hint == lir.EllipseHint(center=(2, 2), rx=1, ry=0.5)


def test_a_text_in_a_space_sits_at_its_mapped_point(document: Make) -> None:
    label = {"id": "t", "type": "text", "text": "x", "in": "P", "at": [1, 1]}
    (item,) = items(document([label], spaces=[{"id": "P", "origin": [0, 1], "unit": 2}]), "t")
    assert item.at == (2, 3)
