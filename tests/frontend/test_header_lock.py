"""check_header: the IR must carry the header the orchestrator locked."""

import copy
from collections.abc import Callable
from typing import Any

from irpipe.artifacts import IR, LOCKED_HEADER
from irpipe.core import Pipeline, RunResult
from irpipe.frontend.header_lock import CheckHeader, differences
from irpipe.schema.ir import IRDocument, header_hash

type Build = Callable[..., dict[str, Any]]


def check(locked: dict[str, Any], written: dict[str, Any]) -> RunResult:
    header = IRDocument.model_validate(locked).header
    document = IRDocument.model_validate(written)
    pipeline = Pipeline([CheckHeader()], inputs=[IR, LOCKED_HEADER])
    return pipeline.run({IR: document, LOCKED_HEADER: header})


def test_the_same_header_passes(ir: Build) -> None:
    assert check(ir(), ir()).issues == ()


def test_spacing_key_order_and_9_versus_9_0_do_not_change_the_hash(ir: Build) -> None:
    first = IRDocument.model_validate(ir()).header
    reordered = dict(reversed(list(ir().items())))
    reordered["frame"]["units"] = [16.0, 9.0]
    assert header_hash(IRDocument.model_validate(reordered).header) == header_hash(first)


def test_a_changed_header_names_what_changed(ir: Build) -> None:
    changed = ir()
    changed["colors"]["a"] = "#FF0000"
    changed["frame"]["safe"] = [-8, -4.5, 8, 4.5]
    (issue,) = check(ir(), changed).issues
    assert (issue.code, issue.origin) == ("E-HEADER", "ir")
    assert issue.message == (
        "the header was changed at colors.a, frame.safe[0], frame.safe[1], frame.safe[2], "
        "frame.safe[3]"
    )
    assert issue.path == "colors.a"


def test_a_long_list_of_changes_is_cut_short(ir: Build) -> None:
    changed = copy.deepcopy(ir())
    changed["typography"]["sizes"] = {k: 10 for k in changed["typography"]["sizes"]}
    changed["intent"] = "something else"
    (issue,) = check(ir(), changed).issues
    assert issue.message.endswith("and 1 more")


def test_differences_walks_nested_objects_and_lists() -> None:
    locked = {"a": {"b": [1, 2]}, "c": 1}
    written = {"a": {"b": [1, 3]}, "c": 1, "d": 2}
    assert differences(locked, written) == ["a.b[1]", "d"]
