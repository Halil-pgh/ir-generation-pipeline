"""Shapes and group transforms: SVG and Manim agree.

These pictures come from an IR, through the front-end, so every shape
reaches the backends as the front-end draws it: its subpaths for SVG,
and its hint for Manim, which draws it with its own class.
"""

from typing import Any

import pytest

pytestmark = pytest.mark.manim

FILL = {"fill": "a", "color": "b", "stroke_width": 6}


def test_every_named_shape(bench: Any, ir_text: Any) -> None:
    shapes = [
        {"id": "circle", "type": "circle", "center": [-6, 2.5], "radius": 1, **FILL},
        {"id": "ellipse", "type": "ellipse", "center": [-3, 2.5], "rx": 1.4, "ry": 0.8, **FILL},
        {"id": "rect", "type": "rect", "center": [0.5, 2.5], "width": 2.5, "height": 1.5, **FILL},
        {
            "id": "rounded",
            "type": "rect",
            "center": [4, 2.5],
            "width": 2.5,
            "height": 1.5,
            "corner_radius": 0.4,
            **FILL,
        },
        {
            "id": "triangle",
            "type": "regular_polygon",
            "center": [-6, -0.5],
            "radius": 1.1,
            "sides": 3,
            **FILL,
        },
        {
            "id": "hexagon",
            "type": "regular_polygon",
            "center": [-3, -0.5],
            "radius": 1.1,
            "sides": 6,
            "rotation": 15,
            **FILL,
        },
        {
            "id": "polygon",
            "type": "polygon",
            "points": [[-0.5, -1.5], [1.5, -1], [0.5, 0.5]],
            **FILL,
        },
        {
            "id": "sector",
            "type": "sector",
            "center": [4, -1],
            "radius": 1.4,
            "start_angle": 20,
            "end_angle": 250,
            **FILL,
        },
        {"id": "line", "type": "line", "start": [-6.5, -3], "end": [-4, -2.5], "stroke_width": 8},
        {
            "id": "arc",
            "type": "arc",
            "center": [-1.5, -3],
            "radius": 1,
            "start_angle": 0,
            "end_angle": 140,
            "stroke_width": 8,
        },
        {
            "id": "polyline",
            "type": "polyline",
            "points": [[1, -3.5], [2, -2.5], [3, -3.5], [4, -2.5]],
            "stroke_width": 8,
        },
        {"id": "arrow", "type": "line", "start": [5, -3.5], "end": [7, -2.5], "arrows": ["end"]},
    ]
    bench.ir(ir_text(shapes)).assert_alike()


def box(oid: str, center: list[float]) -> dict[str, Any]:
    return {"id": oid, "type": "rect", "center": center, "width": 1.6, "height": 0.8, **FILL}


def test_transforms_with_exact_numbers(bench: Any, ir_text: Any) -> None:
    objects = [
        box("a", [0, 0]),
        box("b", [0, 0]),
        box("c", [0, 0]),
        {"id": "quarter", "type": "group", "children": ["a"], "rotate": 90, "translate": [-5, 0]},
        {"id": "double", "type": "group", "children": ["b"], "scale": 2, "translate": [0, 1]},
        {"id": "inner", "type": "group", "children": ["c"], "translate": [1, 0]},
        {
            "id": "outer",
            "type": "group",
            "children": ["inner"],
            "rotate": 180,
            "translate": [5, -2],
        },
    ]
    bench.ir(ir_text(objects)).assert_alike()


@pytest.mark.xfail(
    strict=True,
    raises=pytest.fail.Exception,  # the pictures differ, nothing else
    reason="S5: the SVG writer rounds group matrices to 3 decimals; up to 0.6 px off at 1080p",
)
def test_a_turn_by_an_inexact_angle(bench: Any, ir_text: Any) -> None:
    outline = {"id": "a", "type": "rect", "center": [0, 0], "width": 3, "height": 1.5}
    turned = {
        "id": "turned",
        "type": "group",
        "children": ["a"],
        "rotate": 28.65,
        "translate": [-4, 0],
    }
    bench.ir(ir_text([{**outline, "stroke_width": 6}, turned])).assert_alike()


@pytest.mark.xfail(
    strict=True,
    raises=pytest.fail.Exception,  # the pictures differ, nothing else
    reason="step 14: under an uneven scale strokes scale by the square root of the area factor; "
    "SVG stretches them",
)
def test_an_uneven_scale(bench: Any, ir_text: Any) -> None:
    ring = {"id": "ring", "type": "circle", "center": [0, 0], "radius": 1, "stroke_width": 8}
    objects = [ring, {"id": "wide", "type": "group", "children": ["ring"], "scale": [3, 1]}]
    bench.ir(ir_text(objects)).assert_alike()
