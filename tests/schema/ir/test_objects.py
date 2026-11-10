"""The core objects: what each type accepts and refuses.

The example picture is a vector projection: two vectors from the origin, the
projection of ``a`` onto ``b``, a dashed construction line and two labels.
"""

from typing import Any

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from irpipe.schema.ir import (
    Arc,
    Circle,
    Ellipse,
    Group,
    IRBody,
    IRObject,
    Line,
    Path,
    Polygon,
    Polyline,
    Rect,
    RegularPolygon,
    Sector,
    Text,
)

OBJECT = TypeAdapter(IRObject)

EXAMPLES: list[tuple[type, dict[str, Any]]] = [
    (Circle, {"id": "origin", "type": "circle", "center": [0, 0], "radius": 0.08, "fill": "a"}),
    (Ellipse, {"id": "orbit", "type": "ellipse", "center": [0, 0], "rx": 3, "ry": 1.5}),
    (Rect, {"id": "panel", "type": "rect", "center": [0, 3], "width": 6, "height": 2}),
    (
        RegularPolygon,
        {"id": "hex", "type": "regular_polygon", "center": [0, 0], "radius": 1, "sides": 6},
    ),
    (Polygon, {"id": "tri", "type": "polygon", "points": [[0, 0], [2, 0], [0, 1]]}),
    (
        Sector,
        {
            "id": "pie",
            "type": "sector",
            "center": [0, 0],
            "radius": 1,
            "start_angle": 0,
            "end_angle": 120,
        },
    ),
    (Line, {"id": "a", "type": "line", "start": [0, 0], "end": [3, 2], "color": "a"}),
    (Polyline, {"id": "zig", "type": "polyline", "points": [[0, 0], [1, 1], [2, 0]]}),
    (
        Arc,
        {
            "id": "theta",
            "type": "arc",
            "center": [0, 0],
            "radius": 0.6,
            "start_angle": 0,
            "end_angle": 56.3,
        },
    ),
    (
        Path,
        {
            "id": "arc",
            "type": "path",
            "subpaths": [{"start": [1, 0], "segments": [{"quad": [[1, 0.5], [0.8, 0.6]]}]}],
        },
    ),
    (Text, {"id": "a_label", "type": "text", "text": "a", "at": [3.1, 2.1]}),
    (Group, {"id": "vectors", "type": "group", "children": ["a", "b"]}),
]


def validate(data: dict[str, Any]) -> Any:
    return OBJECT.validate_python(data)


@pytest.mark.parametrize(("model", "data"), EXAMPLES)
def test_the_type_field_picks_the_model(model: type, data: dict[str, Any]) -> None:
    assert type(validate(data)) is model


def test_an_unknown_type_lists_the_known_ones() -> None:
    known = "'circle', 'ellipse', 'rect', 'regular_polygon', 'polygon', 'sector', 'line', "
    known += "'polyline', 'arc', 'path', 'text', 'math', 'group', 'stack'"
    with pytest.raises(ValidationError, match=known):
        validate({"id": "s", "type": "spring"})


def test_the_type_field_is_required() -> None:
    with pytest.raises(ValidationError, match="discriminator 'type'"):
        validate({"id": "c", "center": [0, 0], "radius": 1})


@pytest.mark.parametrize("bad_id", ["2b", "v.label", "proj-ab", ""])
def test_ids_are_names_without_dots(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="id"):
        validate({"id": bad_id, "type": "circle", "center": [0, 0], "radius": 1})


def test_a_misspelled_field_is_refused() -> None:
    with pytest.raises(ValidationError, match="raduis"):
        validate({"id": "c", "type": "circle", "center": [0, 0], "raduis": 1})


# Paint and text


@pytest.mark.parametrize("color", ["#FFD43B", "a", "proj_ab", [88, 196, 221], "none"])
def test_a_color_is_literal_named_or_none(color: Any) -> None:
    validate({"id": "a", "type": "line", "start": [0, 0], "end": [1, 1], "color": color})


@pytest.mark.parametrize("color", ["#FFF", "#FFD43BAA", [256, 0, 0], [1, 2], "a b"])
def test_a_malformed_color_is_refused(color: Any) -> None:
    with pytest.raises(ValidationError, match="color"):
        validate({"id": "a", "type": "line", "start": [0, 0], "end": [1, 1], "color": color})


@pytest.mark.parametrize(("size", "ok"), [("label", True), (38, True), ("tiny", False), (0, False)])
def test_a_text_size_is_a_role_or_reference_pixels(size: Any, ok: bool) -> None:
    data = {"id": "t", "type": "text", "text": "a", "at": [0, 0], "size": size}
    if ok:
        validate(data)
    else:
        with pytest.raises(ValidationError, match="size"):
            validate(data)


def test_a_text_anchor_left_out_stays_unset_for_place_to_fill() -> None:
    text = validate({"id": "t", "type": "text", "text": "a", "at": [0, 0]})
    assert text.anchor is None  # place reads it as "center"
    with pytest.raises(ValidationError, match="anchor"):
        validate({"id": "t", "type": "text", "text": "a", "at": [0, 0], "anchor": "middle"})


def test_style_names_one_class_or_several() -> None:
    one = validate({"id": "a", "type": "line", "start": [0, 0], "end": [1, 1], "style": "muted"})
    two = validate(
        {"id": "a", "type": "line", "start": [0, 0], "end": [1, 1], "style": ["muted", "dashed"]}
    )
    assert one.style_names == ("muted",)
    assert two.style_names == ("muted", "dashed")


def test_opacity_is_between_zero_and_one() -> None:
    with pytest.raises(ValidationError, match="opacity"):
        validate({"id": "c", "type": "circle", "center": [0, 0], "radius": 1, "opacity": 1.5})


# Paths and groups


def test_a_path_mixes_straight_and_bezier_segments() -> None:
    path = validate(
        {
            "id": "blob",
            "type": "path",
            "subpaths": [
                {
                    "start": [0, 0],
                    "segments": [
                        {"line": [2, 0]},
                        {"quad": [[3, 1], [2, 2]]},
                        {"cubic": [[1, 3], [0, 2], [0, 1]]},
                    ],
                    "closed": True,
                }
            ],
            "fill_rule": "evenodd",
        }
    )
    assert len(path.subpaths[0].segments) == 3


@pytest.mark.parametrize(
    "subpaths",
    [
        [],
        [{"start": [0, 0], "segments": []}],
        [{"start": [0, 0], "segments": [{"arc": [1, 1]}]}],
    ],
)
def test_a_path_needs_real_segments(subpaths: list[Any]) -> None:
    with pytest.raises(ValidationError):
        validate({"id": "p", "type": "path", "subpaths": subpaths})


def test_a_group_needs_children_and_scales_by_one_or_two_factors() -> None:
    with pytest.raises(ValidationError, match="children"):
        validate({"id": "g", "type": "group", "children": []})
    group = validate({"id": "g", "type": "group", "children": ["a"], "scale": [2, 0.5]})
    assert group.scale == (2, 0.5)
    assert group.translate == (0, 0)


# A whole body


PROJECTION_BODY: dict[str, Any] = {
    "focus": ["proj_ab"],
    "objects": [
        {"id": "a", "type": "line", "start": [0, 0], "end": [2, 3], "color": "a"},
        {"id": "b", "type": "line", "start": [0, 0], "end": [4, 0], "color": "b"},
        {"id": "proj_ab", "type": "line", "start": [0, 0], "end": [2, 0], "color": "proj"},
        {
            "id": "drop",
            "type": "line",
            "start": [2, 3],
            "end": [2, 0],
            "style": "construction",
        },
        {"id": "a_label", "type": "text", "text": "a", "at": [2.1, 3.1], "size": "label"},
        {"id": "b_label", "type": "text", "text": "b", "at": [4.1, -0.3], "size": "label"},
        {"id": "vectors", "type": "group", "children": ["a", "b", "proj_ab"]},
    ],
}


def test_a_body_survives_json_and_has_a_schema() -> None:
    body = IRBody.model_validate(PROJECTION_BODY)
    assert IRBody.model_validate_json(body.model_dump_json()) == body
    schema = str(IRBody.model_json_schema())
    for name in ("Circle", "Rect", "Line", "Path", "Text", "Group"):
        assert name in schema


# The basic shapes' own rules


@pytest.mark.parametrize(
    ("data", "field"),
    [
        ({"type": "polygon", "points": [[0, 0], [1, 1]]}, "points"),
        ({"type": "polyline", "points": [[0, 0]]}, "points"),
        ({"type": "regular_polygon", "center": [0, 0], "radius": 1, "sides": 2}, "sides"),
        ({"type": "ellipse", "center": [0, 0], "rx": 1, "ry": 0}, "ry"),
    ],
)
def test_a_shape_needs_enough_to_be_a_shape(data: dict[str, Any], field: str) -> None:
    with pytest.raises(ValidationError, match=field):
        validate({"id": "s", **data})


@pytest.mark.parametrize("kind", ["arc", "sector"])
@pytest.mark.parametrize(
    ("start", "end", "message"),
    [(10, 10, "has no length"), (0, 400, "at most 360"), (90, -300, "at most 360")],
)
def test_an_arc_sweeps_somewhere_but_at_most_once_around(
    kind: str, start: float, end: float, message: str
) -> None:
    data = {"id": "a", "type": kind, "center": [0, 0], "radius": 1}
    with pytest.raises(ValidationError, match=message):
        validate({**data, "start_angle": start, "end_angle": end})


@pytest.mark.parametrize("model", [Line, Polyline, Arc])
def test_open_shapes_have_no_fill(model: type[BaseModel]) -> None:
    assert "fill" not in model.model_fields


# Points, boxes, stacks, labels and arrows (placement)


@pytest.mark.parametrize(
    "point",
    [[1, "2*1"], "v.tip", "safe.center_top", "v.label.left_top", {"on": "f", "t": 0.5},
     {"on": "f", "x": "1/2"}],
)  # fmt: skip
def test_a_point_is_numbers_or_a_reference(point: Any) -> None:
    validate({"id": "c", "type": "circle", "center": point, "radius": 1})


@pytest.mark.parametrize(
    ("point", "message"),
    [
        ("vtip", "valid"),
        ({"on": "f"}, "either t or x"),
        ({"on": "f", "t": 0.5, "x": 1}, "either t or x"),
        ({"on": "f", "t": 2}, "less than or equal to 1"),
    ],
)
def test_a_point_of_no_known_form_is_refused(point: Any, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        validate({"id": "c", "type": "circle", "center": point, "radius": 1})


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"at": [0, 0], "next_to": "c"}, "at or next_to, not both"),
        ({"at": [0, 0], "anchor": "center", "dir": "up"}, "give one"),
        ({"next_to": "c", "anchor": "center"}, "not with anchor"),
        ({"at": [0, 0], "gap": 0.2}, "it needs dir"),
        ({"at": [0, 0], "dir": [0, 0]}, "points nowhere"),
    ],
)
def test_a_box_is_placed_one_way(fields: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        validate({"id": "t", "type": "text", "text": "x", **fields})


def test_a_box_may_sit_beside_a_point_or_next_to_an_object() -> None:
    beside = validate({"id": "t", "type": "text", "text": "x", "at": "v.tip", "dir": 135.0})
    assert beside.dir == 135
    nearby = validate({"id": "t", "type": "math", "tex": "x", "next_to": "c", "gap": 0})
    assert (nearby.next_to, nearby.dir) == ("c", None)


def test_a_grid_stack_needs_columns_and_only_a_grid_takes_them() -> None:
    stack = {"id": "s", "type": "stack", "children": ["a", "b"]}
    assert validate(stack).arrange == "column"
    with pytest.raises(ValidationError, match="a grid needs columns"):
        validate({**stack, "arrange": "grid"})
    with pytest.raises(ValidationError, match="a grid needs columns"):
        validate({**stack, "columns": 2})
    assert validate({**stack, "arrange": "grid", "columns": 2}).columns == 2


@pytest.mark.parametrize(
    ("label", "message"),
    [
        ({}, "either text or tex"),
        ({"text": "a", "tex": "a"}, "either text or tex"),
        ({"text": "a", "gap": 0.1}, "it needs dir"),
        ({"tex": "a", "weight": "bold"}, "TeX sets its own"),
        ({"text": "a", "at": "Tip"}, "pattern"),
    ],
)
def test_a_label_is_a_text_or_a_formula(label: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        validate({"id": "l", "type": "line", "start": [0, 0], "end": [1, 0], "label": label})


def test_arrows_go_on_open_shapes_once_each() -> None:
    line = {"id": "l", "type": "line", "start": [0, 0], "end": [1, 0]}
    assert validate({**line, "arrows": ["start", "end"]}).arrows == ("start", "end")
    with pytest.raises(ValidationError, match="listed once"):
        validate({**line, "arrows": ["end", "end"]})
    with pytest.raises(ValidationError, match="arrows"):
        validate({"id": "c", "type": "circle", "center": [0, 0], "radius": 1, "arrows": ["end"]})


def test_in_names_a_space_and_is_written_back_as_in() -> None:
    circle = validate({"id": "c", "type": "circle", "center": [0, 0], "radius": 1, "in": "P"})
    assert circle.space == "P"
    assert circle.model_dump(exclude_defaults=True)["in"] == "P"
    with pytest.raises(ValidationError, match="space"):
        validate({"id": "c", "type": "circle", "center": [0, 0], "radius": 1, "space": "P"})
