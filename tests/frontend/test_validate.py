"""validate: every problem comes back as an issue with a JSON path, in the IR's terms."""

from collections.abc import Callable
from typing import Any

import pytest

from irpipe.artifacts import IR, IR_SOURCE
from irpipe.core import Issue, Pipeline, RunResult
from irpipe.frontend.normalize import W_UNDECLARED_COLOR
from irpipe.frontend.validate import Validate
from irpipe.schema.ir import IRDocument

CIRCLE = {"id": "c", "type": "circle", "center": [0, 0], "radius": 1}
LINE = {"id": "l", "type": "line", "start": [0, 0], "end": [1, 1]}


def run(text: str) -> RunResult:
    return Pipeline([Validate()], inputs=[IR_SOURCE]).run({IR_SOURCE: text})


def only(result: RunResult) -> Issue:
    (issue,) = result.issues
    return issue


@pytest.fixture
def check(ir_text: Callable[..., str]) -> Callable[..., RunResult]:
    return lambda *args, **kwargs: run(ir_text(*args, **kwargs))


def test_a_valid_ir_is_handed_on(check: Callable[..., RunResult]) -> None:
    result = check([CIRCLE, LINE])
    assert result.issues == ()
    assert isinstance(result.get(IR), IRDocument)


# E-JSON and E-SCHEMA


def test_text_that_is_not_json_says_where_reading_stopped() -> None:
    result = run('{"version": "frame-ir/1.0",\n "objects": [}')
    issue = only(result)
    assert (issue.code, issue.message) == ("E-JSON", "Expecting value at line 2, column 14")
    assert result.stopped_at == "validate"


def test_ir_json_holds_one_object() -> None:
    assert only(run("[1, 2]")).message == "ir.json must hold one JSON object"


def test_an_unknown_field_gets_its_path_and_a_suggestion(
    check: Callable[..., RunResult],
) -> None:
    circle = {"id": "c", "type": "circle", "center": [0, 0], "radius": 1, "colour": "a"}
    issue = only(check([LINE, circle]))
    assert (issue.code, issue.path, issue.message) == (
        "E-SCHEMA",
        "objects[1].colour",
        "unknown field 'colour'",
    )
    assert issue.hint == "did you mean 'color'?"


def test_a_missing_field_is_named(check: Callable[..., RunResult]) -> None:
    issue = only(check([{"id": "c", "type": "circle", "center": [0, 0]}]))
    assert (issue.path, issue.message) == ("objects[0].radius", "missing field 'radius'")


def test_an_unknown_type_gets_a_suggestion(check: Callable[..., RunResult]) -> None:
    issue = only(check([{"id": "c", "type": "cirlce", "center": [0, 0], "radius": 1}]))
    assert (issue.path, issue.message, issue.hint) == (
        "objects[0]",
        "unknown type 'cirlce'",
        "did you mean 'circle'?",
    )


@pytest.mark.parametrize(
    ("field", "value", "hint_start"),
    [
        ("color", "#FFD43BAA", 'a color is "#RRGGBB"'),
        ("color", [256, 0, 0], 'a color is "#RRGGBB"'),
        ("style", 3, "a style class name"),
    ],
)
def test_a_value_of_no_allowed_form_is_one_issue_naming_the_forms(
    check: Callable[..., RunResult], field: str, value: Any, hint_start: str
) -> None:
    issue = only(check([{**LINE, field: value}]))
    assert issue.path == f"objects[0].{field}"
    assert issue.message.endswith("fits none of the allowed forms")
    assert issue.hint is not None and issue.hint.startswith(hint_start)


def test_a_broken_segment_is_reported_once(check: Callable[..., RunResult]) -> None:
    path = {"id": "p", "type": "path", "subpaths": [{"start": [0, 0], "segments": [{"arc": 1}]}]}
    issue = only(check([path]))
    assert issue.path == "objects[0].subpaths[0].segments[0]"


def test_an_empty_list_says_how_many_items_it_needs(check: Callable[..., RunResult]) -> None:
    issue = only(check([{"id": "p", "type": "path", "subpaths": []}]))
    assert (issue.path, issue.message) == ("objects[0].subpaths", "needs at least 1 item")


def test_a_rule_a_shape_checks_itself_reads_plainly(check: Callable[..., RunResult]) -> None:
    arc = {"id": "t", "type": "arc", "center": [0, 0], "radius": 1}
    issue = only(check([{**arc, "start_angle": 30, "end_angle": 30}]))
    assert (issue.path, issue.message) == (
        "objects[0]",
        "start_angle and end_angle are equal, so the arc has no length",
    )


# E-ID, E-REF, E-GROUP


def test_an_id_used_twice_names_the_first_user(check: Callable[..., RunResult]) -> None:
    issue = only(check([CIRCLE], defs=[{**LINE, "id": "c"}]))
    assert (issue.code, issue.path, issue.message) == (
        "E-ID",
        "objects[0].id",
        "id 'c' is already used by defs[0]",
    )


@pytest.mark.parametrize(
    ("body", "path", "message", "hint"),
    [
        (
            {"focus": ["cc"]},
            "focus[0]",
            "focus names 'cc', which is not an object",
            "did you mean 'c'?",
        ),
        (
            {"objects": [{**CIRCLE, "style": "mutde"}]},
            "objects[0].style",
            "style class 'mutde' is not in the header's styles",
            "did you mean 'muted'?",
        ),
        (
            {"objects": [{**CIRCLE, "style": ["muted", "dahsed"]}]},
            "objects[0].style[1]",
            "style class 'dahsed' is not in the header's styles",
            "did you mean 'dashed'?",
        ),
        (
            {"objects": [{**CIRCLE, "fill": "bb"}]},
            "objects[0].fill",
            "color 'bb' is not defined in colors",
            "did you mean 'b'?",
        ),
    ],
)
def test_a_name_that_points_at_nothing(
    check: Callable[..., RunResult], body: dict[str, Any], path: str, message: str, hint: str
) -> None:
    objects = body.pop("objects", [CIRCLE])
    issue = only(check(objects, **body))
    assert (issue.code, issue.path, issue.message, issue.hint) == ("E-REF", path, message, hint)


def test_a_header_style_may_only_use_header_colors(check: Callable[..., RunResult]) -> None:
    result = check(
        [CIRCLE],
        styles={"glow": {"color": "AB"}},
        extra_colors={"AB": {"mix": ["a", "b"]}},
    )
    assert only(result).message == "color 'AB' is not defined in the header's colors"


def test_a_mix_is_made_of_two_real_colors(check: Callable[..., RunResult]) -> None:
    result = check([CIRCLE], extra_colors={"AB": {"mix": ["a", "none"]}})
    assert only(result).message == "a mix needs two colors, and 'none' is no color"


@pytest.mark.parametrize(
    ("objects", "defs", "message"),
    [
        ([{"id": "g", "type": "group", "children": ["g"]}], [], "group 'g' lists itself"),
        (
            [CIRCLE, {"id": "g", "type": "group", "children": ["c", "c"]}],
            [],
            "group 'g' lists 'c' twice",
        ),
        (
            [{"id": "g", "type": "group", "children": ["d"]}],
            [{**CIRCLE, "id": "d"}],
            "group 'g' lists def 'd'; defs are never drawn",
        ),
        (
            [
                CIRCLE,
                {"id": "g", "type": "group", "children": ["c"]},
                {"id": "h", "type": "group", "children": ["c"]},
            ],
            [],
            "'c' is already in group 'g'; an object belongs to at most one group or stack",
        ),
    ],
)
def test_a_group_built_wrongly(
    check: Callable[..., RunResult],
    objects: list[dict[str, Any]],
    defs: list[dict[str, Any]],
    message: str,
) -> None:
    issue = only(check(objects, defs=defs))
    assert (issue.code, issue.message) == ("E-GROUP", message)


def test_groups_that_contain_each_other_are_a_loop(check: Callable[..., RunResult]) -> None:
    groups = [
        {"id": "g", "type": "group", "children": ["h"]},
        {"id": "h", "type": "group", "children": ["g"]},
    ]
    issue = only(check(groups))
    assert issue.message == "groups or stacks contain each other: g -> h -> g"
    assert issue.path == "objects[0]"


def test_a_group_child_that_does_not_exist_gets_a_suggestion(
    check: Callable[..., RunResult],
) -> None:
    issue = only(check([CIRCLE, {"id": "g", "type": "group", "children": ["cc"]}]))
    assert (issue.code, issue.hint) == ("E-REF", "did you mean 'c'?")


# E-ALLOW


def test_a_bad_allow_entry_is_reported_but_the_ir_is_still_handed_on(
    check: Callable[..., RunResult],
) -> None:
    result = check([CIRCLE], allow=[{"code": "E-REF", "objects": ["c"], "reason": "ok"}])
    assert {issue.code for issue in result.issues} == {"E-ALLOW"}
    assert result.stopped_at is None
    assert isinstance(result.get(IR), IRDocument)


def test_an_error_in_a_text_is_placed_on_the_right_field(check: Callable[..., RunResult]) -> None:
    text = {"id": "t", "type": "text", "text": "x", "at": [0, 0], "anchor": "middle"}
    issue = only(check([text]))
    assert issue.path == "objects[0].anchor"  # not under its "text" field, which shares the tag


# References, spaces, next_to and labels

V = {"id": "v", "type": "line", "start": [0, 0], "end": [2, 1]}


def text_at(at: Any, **fields: Any) -> dict[str, Any]:
    return {"id": "t", "type": "text", "text": "x", "at": at, **fields}


@pytest.mark.parametrize(
    ("objects", "path", "message", "hint"),
    [
        (
            [V, text_at("vv.tip")],
            "objects[1].at",
            "'vv.tip' refers to 'vv', which is not an object, zone, frame or safe",
            "did you mean 'v'?",
        ),
        (
            [V, text_at("v.top")],
            "objects[1].at",
            "'v' has no point 'top'",
            "did you mean 'tip'?",
        ),
        (
            [CIRCLE, text_at("c.left_baseline")],
            "objects[1].at",
            "'c' has no point 'left_baseline'",
            "only texts, formulas and stacks have a baseline; 'left_bottom' is the box's",
        ),
        (
            [text_at([0, 0]), {**text_at({"on": "t", "t": 0.5}), "id": "u"}],
            "objects[1].at.on",
            '{"on": "t"} needs a shape to follow, and \'t\' is not one',
            "a point on an outline needs a shape",
        ),
        (
            [{**CIRCLE, "in": "Q"}],
            "objects[0].in",
            "'c' is drawn in space 'Q', which is not in spaces",
            "spaces: none",
        ),
        (
            [{"id": "t", "type": "text", "text": "x", "next_to": "t"}],
            "objects[0].next_to",
            "'t' is next to 't', which is itself",
            None,
        ),
        (
            [{**V, "label": {"text": "v", "at": "tipp"}}],
            "objects[0].label.at",
            "the label of 'v' sits at 'tipp', which line has not",
            "did you mean 'tip'?",
        ),
    ],
)
def test_a_reference_that_names_nothing(
    check: Callable[..., RunResult],
    objects: list[dict[str, Any]],
    path: str,
    message: str,
    hint: str | None,
) -> None:
    issue = only(check(objects))
    assert (issue.code, issue.path, issue.message, issue.hint) == ("E-REF", path, message, hint)


def test_zones_and_the_frame_can_be_named_and_spaces_found(
    check: Callable[..., RunResult],
) -> None:
    objects = [
        text_at("plot.center"),
        {**text_at("frame.left_top"), "id": "u"},
        {**CIRCLE, "in": "P"},
    ]
    result = check(objects, zones={"plot": [0, 0, 2, 2]}, spaces=[{"id": "P", "unit": 2}])
    assert result.issues == ()


def test_frame_and_safe_cannot_be_ids(check: Callable[..., RunResult]) -> None:
    issue = only(check([{**CIRCLE, "id": "safe"}]))
    assert (issue.code, issue.path) == ("E-ID", "objects[0].id")
    assert issue.message == "'safe' names the picture's own box and cannot be an id"


def test_a_zone_and_an_object_cannot_share_a_name(check: Callable[..., RunResult]) -> None:
    issue = only(check([CIRCLE], zones={"c": [0, 0, 1, 1]}))
    assert (issue.code, issue.path, issue.message) == (
        "E-ID",
        "objects[0].id",
        "id 'c' is already used by zones.c",
    )


def test_an_object_in_a_group_and_a_stack_is_in_two_places(
    check: Callable[..., RunResult],
) -> None:
    objects = [
        text_at([0, 0]),
        {"id": "g", "type": "group", "children": ["t"]},
        {"id": "s", "type": "stack", "children": ["t"], "at": [0, 0]},
    ]
    issue = only(check(objects))
    assert (issue.code, issue.message) == (
        "E-GROUP",
        "'t' is already in group 'g'; an object belongs to at most one group or stack",
    )


def test_a_point_of_no_allowed_form_names_the_forms(check: Callable[..., RunResult]) -> None:
    issue = only(check([text_at("vtip")]))
    assert (issue.code, issue.path) == ("E-SCHEMA", "objects[0].at")
    assert issue.hint is not None and issue.hint.startswith("a point is [x, y]")


def test_an_allow_entry_may_name_a_label(check: Callable[..., RunResult]) -> None:
    allow = [{"code": W_UNDECLARED_COLOR.code, "objects": ["v.label"],
              "reason": "the label is meant to stand out"}]  # fmt: skip
    result = check([{**V, "label": {"text": "v"}}], allow=allow)
    assert result.issues == ()
