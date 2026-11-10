"""Component "graph": the curve of an expression, its breaks, and what it can be used for."""

import math
from typing import Any

import pytest

from irpipe.frontend.geometry import areas, curves
from irpipe.frontend.measure import measure
from irpipe.frontend.normalize import normalize
from irpipe.frontend.place import place
from irpipe.metrics.fixed import FixedMetrics
from irpipe.schema import lir
from irpipe.schema.ir import Path

GRAPH = {"id": "f", "type": "graph", "function": "x**2/4", "x_range": [-2, 2], "samples": 41}


def curve(document: Any) -> Any:
    (path,) = [obj for obj in document.objects if obj.id == "f"]
    return path


def ends(subpath: Any) -> list[tuple[float, float]]:
    return [subpath.start, *(segment.cubic[2] for segment in subpath.segments)]


def test_the_curve_runs_through_every_sample(opened: Any) -> None:
    path = curve(opened([GRAPH]))
    assert path.type == "path"
    (subpath,) = path.subpaths
    points = ends(subpath)
    assert len(points) == 41
    assert all(y == pytest.approx(x * x / 4) for x, y in points)
    assert points[0] == pytest.approx((-2, 1))
    assert points[-1] == pytest.approx((2, 1))


def test_its_handles_stay_inside_each_piece_so_it_meets_each_x_once(opened: Any) -> None:
    (subpath,) = curve(opened([{**GRAPH, "function": "sin(4*x)", "samples": 12}])).subpaths
    left = subpath.start[0]
    for segment in subpath.segments:
        (h1, _), (h2, _), (end, _) = segment.cubic
        assert left < h1 < h2 < end
        left = end


def test_it_is_close_to_the_true_curve_between_samples(opened: Any) -> None:
    sine = {**GRAPH, "function": "sin(x)", "x_range": [0, 3], "samples": 30}
    (subpath,) = curve(opened([sine])).subpaths
    lifted = lir.Subpath.model_validate(subpath.model_dump())
    for x, y in curves.flatten(lifted):
        assert y == pytest.approx(math.sin(x), abs=5e-4)  # 0.06 px at 1080p, with 30 samples


def test_negative_x_and_values_work(opened: Any) -> None:
    path = curve(opened([{**GRAPH, "function": "k*x**3", "x_range": [-1, 1]}], values={"k": 2}))
    assert path.subpaths[0].start == (-1, pytest.approx(-2))


def test_it_breaks_where_the_function_is_not_defined(opened: Any) -> None:
    path = curve(opened([{**GRAPH, "function": "sqrt(x)", "x_range": [-1, 1]}]))
    (subpath,) = path.subpaths
    assert subpath.start[0] == pytest.approx(0)
    reciprocal = curve(opened([{**GRAPH, "function": "1/x", "x_range": [-1, 1]}]))
    assert len(reciprocal.subpaths) == 2  # the sample at 0 is missing


def test_it_is_cut_where_it_leaves_y_range(opened: Any) -> None:
    path = curve(opened([{**GRAPH, "y_range": [0, 0.5]}]))
    (subpath,) = path.subpaths
    points = ends(subpath)
    assert points[0] == pytest.approx((-math.sqrt(2), 0.5))  # cut exactly on the edge
    assert points[-1] == pytest.approx((math.sqrt(2), 0.5))
    assert all(0 <= y <= 0.5 for _, y in points)


def test_paint_label_arrows_and_meaning_reach_the_path(opened: Any) -> None:
    fields = {"color": "a", "stroke_width": 6, "label": {"tex": "f"}, "arrows": ["end"]}
    path = curve(opened([{**GRAPH, **fields}]))
    assert (path.color, path.stroke_width, path.label.tex, path.arrows) == ("a", 6, "f", ("end",))
    assert path.tags == ("graph",)


def test_a_region_lies_under_it(opened: Any) -> None:
    region = {"id": "r", "type": "region", "shape": {"under": "f", "x": [0, 2]}}
    document = normalize(opened([GRAPH, region]))
    measured, _ = measure(document, FixedMetrics())
    assert measured is not None
    placed, problems = place(document, measured)
    assert placed is not None, problems
    (shape,) = [obj for obj in placed.objects if obj.id == "r"]
    assert isinstance(shape, Path)  # place wrote the region as a path
    subpaths = [lir.Subpath.model_validate(s.model_dump()) for s in shape.subpaths]
    assert areas.area(subpaths, "evenodd").area == pytest.approx(2 / 3, rel=1e-3)  # x³/12 on 0..2


@pytest.mark.parametrize(
    ("function", "code", "message", "hint"),
    [
        ("x**", "E-EXPR", "expected a number, a name or '(' at character 4", None),
        ("q*x", "E-EXPR", "unknown name 'q'", "the variable is 'x'; other names come from values"),
        ("sqrt(-1 - x**2)", "E-COMPONENT", "y = sqrt(-1 - x**2) is not defined anywhere", None),
    ],
)
def test_a_function_it_cannot_draw(
    refused: Any, function: str, code: str, message: str, hint: str | None
) -> None:
    (issue,) = refused([{**GRAPH, "function": function}])
    assert (issue.code, issue.path) == (code, "objects[0].function")
    assert issue.message.startswith(message.split(",")[0])
    if hint:
        assert issue.hint == hint
