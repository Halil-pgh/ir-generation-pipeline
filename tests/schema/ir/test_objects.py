"""The core objects: what each type accepts and refuses.

The example picture is a vector projection: two vectors from the origin, the
projection of ``a`` onto ``b``, a dashed construction line and two labels.
"""

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from irpipe.schema.ir import Circle, Group, IRBody, IRObject, Line, Path, Rect, Text

OBJECT = TypeAdapter(IRObject)

EXAMPLES: list[tuple[type, dict[str, Any]]] = [
    (Circle, {"id": "origin", "type": "circle", "center": [0, 0], "radius": 0.08, "fill": "a"}),
    (Rect, {"id": "panel", "type": "rect", "center": [0, 3], "width": 6, "height": 2}),
    (Line, {"id": "a", "type": "line", "start": [0, 0], "end": [3, 2], "color": "a"}),
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
    with pytest.raises(ValidationError, match="'circle', 'rect', 'line', 'path', 'text', 'group'"):
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


def test_text_is_centered_on_its_point_unless_told_otherwise() -> None:
    text = validate({"id": "t", "type": "text", "text": "a", "at": [0, 0]})
    assert text.anchor == "center"
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
