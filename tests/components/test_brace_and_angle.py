"""Components "brace" and "angle": their shapes, sides, and labels at their middle."""

import math
from typing import Any

import pytest

from irpipe.frontend.geometry import curves
from irpipe.schema import lir

BRACE = {"id": "br", "type": "brace", "start": [0, 0], "end": [4, 0]}
ANGLE = {"id": "t", "type": "angle", "vertex": [0, 0], "arms": [[2, 0], [1, 1]]}


def only(document: Any) -> Any:
    (obj,) = document.objects
    return obj


def outline(path: Any) -> Any:
    return lir.Subpath.model_validate(path.subpaths[0].model_dump())


# Brace


def test_a_brace_runs_from_start_to_end_with_its_tip_in_the_middle(opened: Any) -> None:
    path = only(opened([BRACE]))
    assert path.type == "path" and path.id == "br" and path.tags == ("brace",)
    subpath = outline(path)
    points = curves.flatten(subpath)
    assert points[0] == pytest.approx((0, 0)) and points[-1] == pytest.approx((4, 0))
    assert min(y for _, y in points) == pytest.approx(-0.25)  # its depth, below a rightward way
    middle, _ = curves.point_at([subpath], 0.5)
    assert middle == pytest.approx((2, -0.25), abs=1e-6)  # mid is the tip


def test_side_left_turns_it_over(opened: Any) -> None:
    points = curves.flatten(outline(only(opened([{**BRACE, "side": "left", "depth": 0.5}]))))
    assert max(y for _, y in points) == pytest.approx(0.5)


def test_its_label_sits_beyond_the_tip_unless_it_says_otherwise(opened: Any) -> None:
    path = only(opened([{**BRACE, "label": {"tex": "4"}}]))
    assert (path.label.at, path.label.dir) == ("mid", (0, -1))
    path = only(opened([{**BRACE, "label": {"tex": "4", "at": "end", "dir": "right"}}]))
    assert (path.label.at, path.label.dir) == ("end", "right")


def test_a_brace_without_length_is_refused(refused: Any) -> None:
    (issue,) = refused([{**BRACE, "end": [0, 0]}])
    assert (issue.code, issue.path) == ("E-COMPONENT", "objects[0].end")
    assert issue.message == "start and end are the same point"


# Angle


def test_an_angle_is_an_arc_counterclockwise_from_the_first_arm(opened: Any) -> None:
    arc = only(opened([ANGLE]))
    assert (arc.type, arc.center, arc.radius) == ("arc", (0, 0), 0.5)
    assert (arc.start_angle, arc.end_angle) == (0, pytest.approx(45))
    other = only(opened([{**ANGLE, "arms": [[1, 1], [2, 0]]}]))  # swapped: the other side
    assert (other.start_angle, other.end_angle) == (pytest.approx(45), pytest.approx(360))


def test_a_right_angle_is_a_square_corner(opened: Any) -> None:
    corner = only(opened([{**ANGLE, "arms": [[2, 0], [0, 3]]}]))
    assert corner.type == "polyline"
    assert corner.points == ((0.35, 0), pytest.approx((0.35, 0.35)), pytest.approx((0, 0.35)))
    forced = only(opened([{**ANGLE, "right": True}]))
    assert forced.type == "polyline"
    assert only(opened([{**ANGLE, "arms": [[2, 0], [0, 3]], "right": False}])).type == "arc"


def test_its_label_sits_on_the_bisector_outside_the_arc(opened: Any) -> None:
    arc = only(opened([{**ANGLE, "label": {"tex": "\\theta"}}]))
    half = math.radians(22.5)
    assert arc.label.at == "mid"
    assert arc.label.dir == (pytest.approx(math.cos(half)), pytest.approx(math.sin(half)))


@pytest.mark.parametrize(
    ("arms", "path", "message"),
    [
        ([[0, 0], [1, 1]], "objects[0].arms[0]", "an arm's point is the vertex itself"),
        ([[1, 1], [2, 2]], "objects[0].arms", "both arms point the same way"),
    ],
)
def test_angles_that_cannot_be_marked(refused: Any, arms: Any, path: str, message: str) -> None:
    (issue,) = refused([{**ANGLE, "arms": arms}])
    assert (issue.code, issue.path, issue.message) == ("E-COMPONENT", path, message)
