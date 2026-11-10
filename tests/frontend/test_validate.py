"""validate: every problem comes back as an issue with a JSON path, in the IR's terms."""

from collections.abc import Callable
from typing import Any

import pytest

from irpipe.artifacts import IR, IR_SOURCE
from irpipe.core import Issue, Pipeline, RunResult
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
            "'c' is already in group 'g'; an object belongs to at most one group",
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
    assert issue.message == "groups contain each other: g -> h -> g"
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
