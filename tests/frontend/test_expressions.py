"""Expressions in an IR: computed while it is validated, every problem with its path."""

import json
from collections.abc import Callable
from typing import Any

import pytest

from irpipe.artifacts import IR, IR_SOURCE
from irpipe.core import Issue, Pipeline, RunResult
from irpipe.frontend.validate import Validate
from irpipe.schema.ir import Circle

CIRCLE = {"id": "c", "type": "circle", "center": [0, 0], "radius": 1}


def run(text: str) -> RunResult:
    return Pipeline([Validate()], inputs=[IR_SOURCE]).run({IR_SOURCE: text})


def only(result: RunResult) -> Issue:
    (issue,) = result.issues
    return issue


@pytest.fixture
def check(ir_text: Callable[..., str]) -> Callable[..., RunResult]:
    return lambda *args, **kwargs: run(ir_text(*args, **kwargs))


def test_geometry_written_as_expressions_holds_numbers(check: Callable[..., RunResult]) -> None:
    circle = {**CIRCLE, "center": ["44/17", "k*2"], "radius": "sqrt(2)/2"}
    result = check([circle], values={"k": "1/3"})
    (drawn,) = result.get(IR).objects
    assert isinstance(drawn, Circle)
    assert drawn.center == pytest.approx((44 / 17, 2 / 3))
    assert drawn.radius == pytest.approx(2**-0.5)
    assert result.get(IR).values == {"k": pytest.approx(1 / 3)}


def test_a_bad_expression_in_the_geometry_has_the_fields_path(
    check: Callable[..., RunResult],
) -> None:
    result = check([{**CIRCLE, "center": [0, "sqrt(-1)"]}])
    issue = only(result)
    assert (issue.code, issue.path, issue.message) == (
        "E-EXPR",
        "objects[0].center[1]",
        "square root of a negative number",
    )
    assert result.stopped_at == "validate"


def test_an_unknown_name_gets_a_suggestion(check: Callable[..., RunResult]) -> None:
    issue = only(check([{**CIRCLE, "radius": "rr/2"}], values={"r": 2}))
    assert (issue.code, issue.message, issue.hint) == (
        "E-EXPR",
        "unknown name 'rr'",
        "did you mean 'r'?",
    )


def test_an_expression_wins_over_the_fields_other_forms(
    check: Callable[..., RunResult],
) -> None:
    group = {"id": "g", "type": "group", "children": ["c"], "scale": "1/0"}
    issue = only(check([CIRCLE, group]))
    assert (issue.code, issue.path, issue.message) == (
        "E-EXPR",
        "objects[1].scale",
        "division by zero",
    )


def test_a_bad_value_is_named(check: Callable[..., RunResult]) -> None:
    issue = only(check([CIRCLE], values={"r": 2, "half": "r/"}))
    assert (issue.code, issue.path) == ("E-EXPR", "values.half")


def test_values_in_a_loop_are_e_cycle(check: Callable[..., RunResult]) -> None:
    issue = only(check([CIRCLE], values={"a": "b + 1", "b": "a*2"}))
    assert (issue.code, issue.path, issue.message) == (
        "E-CYCLE",
        "values.a",
        "values refer to each other in a loop: a -> b -> a",
    )


def test_a_value_shaped_wrongly_is_a_schema_problem(check: Callable[..., RunResult]) -> None:
    issue = only(check([CIRCLE], values={"r": [1, 2]}))
    assert (issue.code, issue.path) == ("E-SCHEMA", "values.r")


def test_header_numbers_are_not_expressions(ir: Callable[..., dict[str, Any]]) -> None:
    data = ir([CIRCLE])
    data["frame"]["safe"] = ["-7.6", -4.1, 7.6, 4.1]
    issue = only(run(json.dumps(data)))
    assert (issue.code, issue.path) == ("E-SCHEMA", "frame.safe[0]")


@pytest.mark.parametrize(
    ("field", "value"),
    [("opacity", "0.5"), ("stroke_width", "3"), ("z", "1")],
)
def test_text_is_never_a_number_where_no_expression_is_allowed(
    check: Callable[..., RunResult], field: str, value: str
) -> None:
    issue = only(check([{**CIRCLE, field: value}]))
    assert (issue.code, issue.path) == ("E-SCHEMA", f"objects[0].{field}")


def test_booleans_are_only_true_and_false(check: Callable[..., RunResult]) -> None:
    text = {"id": "t", "type": "text", "text": "x", "at": [0, 0], "italic": "yes"}
    issue = only(check([text]))
    assert (issue.code, issue.path) == ("E-SCHEMA", "objects[0].italic")
