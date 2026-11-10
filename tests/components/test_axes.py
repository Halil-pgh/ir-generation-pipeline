"""Component "axes": where the axes cross, ticks and numbers, names, and sizes in a space."""

from typing import Any

import pytest

AXES = {"id": "ax", "type": "axes", "x_range": [-1, 3], "y_range": [-1, 2]}
SPACE = {"id": "P", "origin": [0, 0], "unit": [2, 0.5]}


def objects(document: Any) -> dict[str, Any]:
    return {obj.id: obj for obj in document.objects}


def test_the_axes_cross_at_zero_and_run_on_into_heads(opened: Any) -> None:
    parts = objects(opened([AXES]))
    x_axis, y_axis = parts["ax.x_axis"], parts["ax.y_axis"]
    assert (x_axis.start, x_axis.end, x_axis.arrows) == ((-1, 0), (3.4, 0), ("end",))
    assert (y_axis.start, y_axis.end) == ((0, -1), (0, 2.4))


def test_they_cross_at_the_nearer_end_when_zero_is_outside(opened: Any) -> None:
    parts = objects(opened([{**AXES, "x_range": [2, 6], "y_range": [1, 3], "arrows": False}]))
    assert (parts["ax.x_axis"].start, parts["ax.x_axis"].end) == ((2, 1), (6, 1))
    assert (parts["ax.y_axis"].start, parts["ax.y_axis"].end) == ((2, 1), (2, 3))


def test_ticks_and_numbers_stand_at_every_step_but_the_crossing(opened: Any) -> None:
    parts = objects(opened([{**AXES, "x_range": [-1, 2, 0.5]}]))
    numbers = [p.tex for oid, p in parts.items() if oid.startswith("ax.x_number_")]
    assert numbers == ["-1", "-0.5", "0.5", "1", "1.5", "2"]
    tick = parts["ax.x_tick_0"]
    assert (tick.start, tick.end) == ((-1, -0.08), (-1, 0.08))
    number = parts["ax.x_number_0"]
    assert (number.at, number.dir, number.gap) == ((-1, -0.08), "down", pytest.approx(0.12))
    assert number.size == "caption"


def test_names_sit_beyond_the_heads(opened: Any) -> None:
    parts = objects(opened([{**AXES, "x_label": "x", "y_label": r"f(x)"}]))
    x_label = parts["ax.x_label"]
    assert (x_label.tex, x_label.at, x_label.dir) == ("x", (3.4, 0), "right")
    assert (parts["ax.y_label"].at, parts["ax.y_label"].dir) == ((0, 2.4), "up")


def test_ticks_and_numbers_can_be_left_out(opened: Any) -> None:
    ids = set(objects(opened([{**AXES, "ticks": False, "numbers": False}])))
    assert ids == {"ax", "ax.x_axis", "ax.y_axis"}


def test_in_a_space_the_fixed_sizes_stay_fixed_on_the_frame(opened: Any) -> None:
    parts = objects(opened([{**AXES, "in": "P"}], spaces=[SPACE]))
    tick = parts["ax.x_tick_0"]  # half a tick is 0.08 frame units: 0.16 space units when uy = 0.5
    assert (tick.start, tick.end, tick.space) == ((-1, -0.16), (-1, 0.16), "P")
    assert parts["ax.x_axis"].end == (pytest.approx(3.2), 0)  # 0.4 frame units: 0.2 when ux = 2


def test_the_axes_are_one_group_and_draw_their_parts_in_order(drawn: Any) -> None:
    (group,) = drawn([AXES]).items
    assert group.id == "ax"
    assert [g.id for g in group.children][:3] == ["ax.x_axis", "ax.y_axis", "ax.x_tick_0"]
    assert {g.source for g in group.children} == {"objects[0]"}


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("x_range", [2, 2], "x_range runs from 2 to 2"),
        ("y_range", [0, 500, 1], "y_range gives 501 ticks; at most 100 are drawn"),
    ],
)
def test_ranges_that_cannot_be_drawn(refused: Any, field: str, value: Any, message: str) -> None:
    (issue,) = refused([{**AXES, field: value}])
    assert (issue.code, issue.path) == ("E-COMPONENT", f"objects[0].{field}")
    assert issue.message == message
