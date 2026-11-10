"""resolve: an IR with absolute positions becomes LIR, one group per object."""

from collections.abc import Callable
from typing import Any

import pytest

from irpipe.artifacts import IR, LIR
from irpipe.core import Pipeline, UnknownPluginError
from irpipe.frontend.resolve import Resolve, Resolver, place_text
from irpipe.metrics import TextBox
from irpipe.metrics.fixed import FixedMetrics
from irpipe.schema import lir
from irpipe.schema.ir import IRDocument

CIRCLE = {"id": "c", "type": "circle", "center": [1, 2], "radius": 0.5, "fill": "a"}
LINE = {"id": "l", "type": "line", "start": [0, 0], "end": [2, 1], "color": "b"}

type Make = Callable[..., IRDocument]


def resolve(document: IRDocument) -> lir.LIRDocument:
    return Resolver(document, FixedMetrics()).resolve()


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
    box = TextBox(width=240, ascent=360, descent=120)  # 2 x 3 x 1 units
    (bx0, _, _, _), found = place_text((0, 0), anchor, box)
    assert (bx0, found) == pytest.approx((x0, baseline))


def test_a_text_without_color_or_size_takes_the_theme_and_body(document: Make) -> None:
    item = first_item(
        resolve(document([{"id": "t", "type": "text", "text": "x", "at": [0, 0]}])).items[0]
    )
    assert (item.color, item.size) == ("#FFFFFF", 42)


# The stage


def test_the_stage_reads_ir_and_writes_lir(document: Make) -> None:
    result = Pipeline([Resolve()], inputs=[IR]).run({IR: document([CIRCLE])})
    assert isinstance(result.get(LIR), lir.LIRDocument)


def test_an_unknown_text_measurer_is_named(document: Make) -> None:
    pipeline = Pipeline([Resolve()], inputs=[IR], options={"resolve": {"metrics": "pang"}})
    with pytest.raises(UnknownPluginError, match="unknown text metrics provider 'pang'"):
        pipeline.run({IR: document([CIRCLE])})


def test_the_light_theme_draws_in_black(ir: Callable[..., dict[str, Any]]) -> None:
    data = ir([{key: value for key, value in LINE.items() if key != "color"}])
    data["frame"]["background"] = "#FAFAFA"
    item = first_item(resolve(IRDocument.model_validate(data)).items[0])
    assert item.stroke.color == "#000000"
