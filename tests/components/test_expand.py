"""The component mechanism: a component is one file, and after validate only core objects remain."""

from typing import Any, Literal, get_args

import pytest

from irpipe.components.base import (
    COMPONENTS,
    Component,
    Context,
    Expansion,
    _check_component,
    group_of,
    make,
)
from irpipe.components.expand import _model_for, document_model, expand_components
from irpipe.core import PluginDefinitionError
from irpipe.frontend.labels import source_paths
from irpipe.frontend.normalize import undeclared_colors
from irpipe.schema.ir import Circle, Group, IRDocument
from irpipe.schema.ir.common import Number
from irpipe.schema.ir.objects import IRObject

CORE_TYPES = {member.model_fields["type"].default for member in get_args(get_args(IRObject)[0])}
AXES = {"id": "ax", "type": "axes", "x_range": [-1, 3], "y_range": [-1, 2]}
GRAPH = {"id": "f", "type": "graph", "function": "x**2/4", "x_range": [-2, 2]}


class Dots(Component):
    """A test component written the way a new one is: a model and its expand."""

    type: Literal["dots"] = "dots"
    count: int
    radius: Number = 0.1

    def expand(self, context: Context) -> Expansion:
        dots = [
            make(Circle, f"{self.id}.dot_{k}", context.values, center=[k, 0], radius=self.radius)
            for k in range(self.count)
        ]
        return Expansion(group_of(self, dots, context.values), dots)


def test_the_four_components_are_registered() -> None:
    assert set(COMPONENTS.names()) >= {"axes", "graph", "brace", "angle"}


def test_without_components_the_document_is_the_core_one() -> None:
    assert _model_for(()) is IRDocument
    assert document_model() is not IRDocument  # the components above are registered


def test_a_new_component_is_one_class(ir: Any) -> None:
    model = _model_for((*(COMPONENTS.get(n) for n in COMPONENTS.names()), Dots))
    raw = ir([{"id": "row", "type": "dots", "count": 3, "radius": "1/4"}, {**GRAPH}])
    document = model.model_validate(raw, context={"values": {}})
    core, issues = expand_components(document, {})
    assert issues == []
    assert [obj.id for obj in core.objects] == ["row", "f", "row.dot_0", "row.dot_1", "row.dot_2"]
    row, dot = core.objects[0], core.objects[2]
    assert isinstance(row, Group)
    assert row.children == ("row.dot_0", "row.dot_1", "row.dot_2")
    assert isinstance(dot, Circle)
    assert dot.radius == 0.25  # its own expressions are computed


def test_a_component_must_say_its_type_and_open() -> None:
    class Nameless(Component):
        def expand(self, context: Context) -> Expansion:
            raise NotImplementedError

    class Closed(Component):
        type: Literal["closed"] = "closed"

    with pytest.raises(PluginDefinitionError, match="needs a literal `type`"):
        _check_component(Nameless)
    with pytest.raises(PluginDefinitionError, match="does not implement expand"):
        _check_component(Closed)


def test_after_validate_only_core_objects_remain(opened: Any) -> None:
    brace = {"id": "b", "type": "brace", "start": [0, 0], "end": [2, 0]}
    angle = {"id": "t", "type": "angle", "vertex": [0, 0], "arms": [[1, 0], [0, 1]]}
    document = opened([AXES, GRAPH, brace, angle])
    assert {obj.type for obj in document.objects} <= CORE_TYPES
    ids = [obj.id for obj in document.objects]
    assert ids[:4] == ["ax", "f", "b", "t"]  # each component keeps its id and its place
    assert all(oid.startswith("ax.") for oid in ids[4:])  # parts come after everything
    assert document.objects[1].tags == ("graph",)  # the meaning stays (analysis §2.7)


def test_a_part_is_reported_at_its_components_place(opened: Any) -> None:
    document = opened([{"id": "c", "type": "circle", "center": [0, 0], "radius": 1}, AXES])
    paths = source_paths(document)
    assert paths["ax"] == paths["ax.x_axis"] == paths["ax.x_tick_0"] == "objects[1]"
    assert paths["c"] == "objects[0]"


def test_a_component_that_cannot_open_is_an_issue_at_its_field(refused: Any) -> None:
    circle = {"id": "c", "type": "circle", "center": [0, 0], "radius": 1}
    (issue,) = refused([circle, {**AXES, "x_range": [3, -1]}])
    assert (issue.code, issue.path, issue.objects) == ("E-COMPONENT", "objects[1].x_range", ("ax",))
    assert issue.message == "x_range runs from 3 to -1"


def test_names_inside_a_component_are_checked_at_its_place(refused: Any) -> None:
    (issue,) = refused([{**AXES, "in": "Q"}])
    assert (issue.code, issue.path) == ("E-REF", "objects[0].in")
    assert "space 'Q'" in issue.message


def test_a_literal_color_is_reported_once_at_the_component(opened: Any) -> None:
    (issue,) = undeclared_colors(opened([{**AXES, "color": "#FFFFFF"}]))  # 13 parts share it
    assert (issue.path, issue.objects) == ("objects[0].color", ("ax",))
    assert issue.code == "W-UNDECLARED-COLOR"


def test_unknown_types_and_fields_get_suggestions_among_components_too(refused: Any) -> None:
    (issue,) = refused([{**AXES, "type": "axis"}])
    assert (issue.message, issue.hint) == ("unknown type 'axis'", "did you mean 'axes'?")
    (issue,) = refused([{**GRAPH, "x_rnage": [0, 1]}])
    assert issue.message == "unknown field 'x_rnage'"
    assert issue.hint == "did you mean 'x_range'?"


def test_component_fields_take_expressions_and_values(opened: Any) -> None:
    document = opened([{**GRAPH, "x_range": ["-k", "k"]}], values={"k": "3/2"})
    start = document.objects[0].subpaths[0].start
    assert start == (-1.5, pytest.approx(0.5625))


def test_focus_and_allow_may_name_components_and_their_parts(opened: Any) -> None:
    allow = [
        {"code": "W-UNDECLARED-COLOR", "objects": ["ax"], "reason": "white axes on purpose here"}
    ]
    document = opened([AXES], focus=["ax"], allow=allow)
    assert document.focus == ("ax",)
