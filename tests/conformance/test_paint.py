"""Strokes, caps, joins, dashes, fills, opacity and drawing order: SVG and Manim agree.

The pictures are drawn straight from a LIR, so the two backends get
exactly the same numbers. Where they are known to part, the test says
why (a strict xfail: it fails loudly the day they agree).
"""

from typing import Any

import pytest

pytestmark = pytest.mark.manim

WHITE = "#FFFFFF"


def line(*points: tuple[float, float], closed: bool = False) -> dict[str, Any]:
    start, *rest = points
    return {"start": list(start), "segments": [{"line": list(p)} for p in rest], "closed": closed}


def rectangle(x0: float, y0: float, x1: float, y1: float) -> dict[str, Any]:
    return line((x0, y0), (x1, y0), (x1, y1), (x0, y1), closed=True)


def circle(cx: float, cy: float, r: float) -> dict[str, Any]:
    """A circle as four cubic pieces, starting at its right."""
    k = 0.5522847498 * r
    return {
        "start": [cx + r, cy],
        "segments": [
            {"cubic": [[cx + r, cy + k], [cx + k, cy + r], [cx, cy + r]]},
            {"cubic": [[cx - k, cy + r], [cx - r, cy + k], [cx - r, cy]]},
            {"cubic": [[cx - r, cy - k], [cx - k, cy - r], [cx, cy - r]]},
            {"cubic": [[cx + k, cy - r], [cx + r, cy - k], [cx + r, cy]]},
        ],
        "closed": True,
    }


def path(*subpaths: dict[str, Any], **paint: Any) -> dict[str, Any]:
    return {"type": "path", "subpaths": list(subpaths), **paint}


def stroke(width: float, **fields: Any) -> dict[str, Any]:
    return {"color": WHITE, "width": width, **fields}


def test_stroke_widths_and_caps(bench: Any, group: Any) -> None:
    widths = [(2, "butt"), (4, "butt"), (8, "round"), (16, "square"), (30, "round")]
    rows = []
    for k, (width, cap) in enumerate(widths):
        y = 3.5 - k * 1.5
        rows.append(group(f"h{k}", path(line((-7, y), (-1, y)), stroke=stroke(width, cap=cap))))
    slants = []
    for k, width in enumerate([2, 4, 8, 16]):
        slants.append(group(f"d{k}", path(line((1 + k, -3), (2 + k, 3)), stroke=stroke(width))))
    bench.lir(rows + slants).assert_alike()


def test_joins_at_open_angles(bench: Any, group: Any) -> None:
    corners = []
    for k, join in enumerate(["miter", "round", "bevel"]):
        x = -6 + 4 * k
        corner = line((x, -1), (x + 1, 2), (x + 2, -1))
        corners.append(group(f"j{k}", path(corner, stroke=stroke(14, join=join))))
    square = group("square", path(rectangle(2, -3, 5, 0), stroke=stroke(12)))
    bench.lir([*corners, square]).assert_alike()


@pytest.mark.xfail(
    strict=True,
    raises=pytest.fail.Exception,  # the pictures differ, nothing else
    reason="S7: no miter limit in the LIR; SVG bevels below 29 degrees (limit 4), cairo at 10",
)
def test_a_sharp_miter_join(bench: Any, group: Any) -> None:
    sharp = path(line((-1, -3), (0, 3), (1, -3)), stroke=stroke(20))
    bench.lir([group("sharp", sharp)]).assert_alike()


def test_dashes(bench: Any, group: Any) -> None:
    blue = {"color": "#3366FF"}
    filled = path(rectangle(2, -4, 5, -1), fill=blue, stroke=stroke(6, dash=[40, 25]))
    dashed = [
        group("plain", path(line((-7, 3), (7, 3)), stroke=stroke(6, dash=[30, 15]))),
        group("odd", path(line((-7, 1.5), (7, 1.5)), stroke=stroke(6, dash=[30, 10, 5]))),
        group("round", path(line((-7, 0), (7, 0)), stroke=stroke(8, dash=[20, 23], cap="round"))),
        group("curve", path(circle(-3, -2.5, 1.5), stroke=stroke(6, dash=[24, 12]))),
        group("filled", filled),
    ]
    bench.lir(dashed).assert_alike()


@pytest.mark.xfail(
    strict=True,
    raises=pytest.fail.Exception,
    reason="S6: lowering drops the zero-length dash at a path's end, which SVG draws as a dot",
)
def test_a_dash_that_ends_where_the_line_ends(bench: Any, group: Any) -> None:
    # 14 units are 1680 px: 42 patterns of 20 + 20, so a zero-length dash falls on the end
    dotted = path(line((-7, 0), (7, 0)), stroke=stroke(8, dash=[20, 20], cap="round"))
    bench.lir([group("dots", dotted)]).assert_alike()


def test_fills_holes_and_fill_with_stroke(bench: Any, group: Any) -> None:
    ring = path(circle(-4, 0, 2), circle(-4, 0, 1), fill={"color": "#83C167", "rule": "evenodd"})
    lens = path(circle(0.5, 0, 1.5), circle(1.5, 0, 1.5), fill={"color": "#58C4DD"})
    frame = path(
        rectangle(4, -2, 7, 2),
        rectangle(5, -1, 6, 1),
        fill={"color": "#FFD43B", "rule": "evenodd"},
        stroke=stroke(6),
    )
    bench.lir([group("ring", ring), group("lens", lens), group("frame", frame)]).assert_alike()


def test_opacity_over_other_paint(bench: Any, group: Any) -> None:
    red = path(circle(-1, 0, 2), fill={"color": "#FF0000", "opacity": 0.5})
    blue = path(
        circle(1, 0, 2),
        fill={"color": "#0000FF", "opacity": 0.5},
        stroke={"color": WHITE, "width": 12, "opacity": 0.4},
    )
    green = path(line((-6, -3), (6, -3)), stroke={"color": "#00FF00", "width": 30, "opacity": 0.3})
    bench.lir([group("red", red), group("blue", blue), group("green", green)]).assert_alike()


def test_drawing_order(bench: Any, group: Any) -> None:
    squares = []
    for k, color in enumerate(["#FF0000", "#00FF00", "#0000FF"]):
        square = rectangle(-3 + k, -2 + k / 2, k, 1 + k / 2)
        squares.append(group(f"s{k}", path(square, fill={"color": color}, stroke=stroke(4)), z=k))
    bench.lir(squares).assert_alike()
