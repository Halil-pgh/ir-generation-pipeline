"""The SVG backend: pixels, groups, paint, text, transforms, and the PNG."""

import math
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

from irpipe.backends.base import Capability
from irpipe.backends.svg import SvgBackend
from irpipe.backends.svg.writer import Frame, num, to_svg
from irpipe.frontend.lower import lower
from irpipe.schema.lir import LIRCanvas

NS = {"svg": "http://www.w3.org/2000/svg"}
TEXT = {
    "type": "text",
    "text": "a",
    "font": "Inter",
    "size": 38,
    "color": "#FFD43B",
    "at": [2, 3],
    "anchor": "left_baseline",
    "box": [2, 2.92, 2.17, 3.24],
    "baseline": 3,
}


def svg(lir: Any) -> ET.Element:
    return ET.fromstring(to_svg(lir))


def find(root: ET.Element, path: str) -> ET.Element:
    found = root.find(path, NS)
    assert found is not None, path
    return found


def png_size(path: Path) -> tuple[int, int]:
    width, height = struct.unpack(">II", path.read_bytes()[16:24])
    return width, height


# The frame


def test_the_svg_is_the_output_size_with_the_background(make_lir: Any) -> None:
    root = svg(make_lir())
    assert (root.get("width"), root.get("height"), root.get("viewBox")) == (
        "1920",
        "1080",
        "0 0 1920 1080",
    )
    assert find(root, "svg:rect").get("fill") == "#0E1117"


def test_units_become_pixels_with_y_pointing_down(
    make_lir: Any, group: Any, line: dict[str, Any]
) -> None:
    path = find(svg(make_lir(group("a", line))), "svg:g/svg:path")
    assert path.get("d") == "M 960 540 L 1440 540"  # (0, 0) is the center; 4 units = 480 px


def test_every_object_is_a_group_with_its_id_and_source(
    make_lir: Any, group: Any, line: dict[str, Any]
) -> None:
    root = svg(make_lir(group("outer", group("a", line, source="objects[0]"), source="objects[1]")))
    outer = find(root, "svg:g")
    assert (outer.get("id"), outer.get("data-source")) == ("outer", "objects[1]")
    assert find(outer, "svg:g").get("id") == "a"


# Paint


def test_widths_and_dashes_scale_with_the_resolution(
    make_lir: Any, group: Any, line: dict[str, Any]
) -> None:
    dashed = {**line, "stroke": {"color": "#FFFFFF", "width": 4, "dash": [14, 10]}}
    four_k = {"units": [16, 9], "pixels": [3840, 2160], "background": "#000000"}
    path = find(svg(make_lir(group("a", dashed), canvas=four_k)), "svg:g/svg:path")
    assert (path.get("stroke-width"), path.get("stroke-dasharray")) == ("8", "28 20")


def test_fill_rule_opacity_cap_and_join_reach_the_svg(make_lir: Any, group: Any) -> None:
    item = {
        "type": "path",
        "subpaths": [
            {"start": [0, 0], "segments": [{"line": [1, 0]}, {"line": [0, 1]}], "closed": True}
        ],
        "fill": {"color": "#FF0000", "opacity": 0.5, "rule": "evenodd"},
        "stroke": {
            "color": "#00FF00",
            "width": 2,
            "opacity": 0.25,
            "cap": "round",
            "join": "bevel",
        },
    }
    path = find(svg(make_lir(group("a", item))), "svg:g/svg:path")
    assert path.get("d", "").endswith("Z")
    assert {k: path.get(k) for k in ("fill", "fill-opacity", "fill-rule")} == {
        "fill": "#FF0000",
        "fill-opacity": "0.5",
        "fill-rule": "evenodd",
    }
    assert {k: path.get(k) for k in ("stroke-opacity", "stroke-linecap", "stroke-linejoin")} == {
        "stroke-opacity": "0.25",
        "stroke-linecap": "round",
        "stroke-linejoin": "bevel",
    }


def test_a_stroke_only_path_is_not_filled(make_lir: Any, group: Any, line: dict[str, Any]) -> None:
    assert find(svg(make_lir(group("a", line))), "svg:g/svg:path").get("fill") == "none"


# Text and formulas


@pytest.mark.parametrize(
    ("anchor", "text_anchor"),
    [("left_baseline", "start"), ("center", "middle"), ("right_top", "end")],
)
def test_text_is_placed_by_its_anchor_and_baseline(
    make_lir: Any, group: Any, anchor: str, text_anchor: str
) -> None:
    text = find(svg(make_lir(group("t", {**TEXT, "anchor": anchor}))), "svg:g/svg:text")
    assert (text.get("x"), text.get("y")) == ("1200", "180")  # at.x and the baseline
    assert text.get("text-anchor") == text_anchor
    assert (text.get("font-family"), text.get("font-size")) == ("Inter, sans-serif", "38")
    assert text.text == "a"


def test_bold_italic_and_special_characters(make_lir: Any, group: Any) -> None:
    item = {**TEXT, "text": "a < b & c", "weight": "bold", "italic": True}
    text = find(svg(make_lir(group("t", item))), "svg:g/svg:text")
    assert (text.get("font-weight"), text.get("font-style")) == ("bold", "italic")
    assert text.text == "a < b & c"


def test_a_formula_is_drawn_from_its_glyphs_once_lowered(make_lir: Any, group: Any) -> None:
    glyph = {"start": [0, 0], "segments": [{"line": [0.1, 0]}, {"line": [0, 0.1]}], "closed": True}
    formula = {
        "type": "math",
        "tex": "x",
        "size": 42,
        "color": "#FFFFFF",
        "at": [0, 0],
        "anchor": "center",
        "box": [-0.1, -0.1, 0.1, 0.1],
        "baseline": -0.05,
        "glyphs": [glyph],
    }
    with pytest.raises(TypeError, match="lower the LIR first"):
        svg(make_lir(group("f", formula)))
    lowered, problems = lower(make_lir(group("f", formula)), SvgBackend.capabilities)
    assert problems == []
    path = find(svg(lowered), "svg:g/svg:path")
    assert path.get("fill") == "#FFFFFF"
    assert path.get("d", "").startswith("M ")


# Transforms


def apply(svg_matrix: str, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = map(float, svg_matrix.removeprefix("matrix(").removesuffix(")").split())
    return a * x + c * y + e, b * x + d * y + f


def test_a_group_matrix_in_units_becomes_the_same_motion_in_pixels() -> None:
    frame = Frame(LIRCanvas(units=(16, 9), pixels=(1920, 1080), background="#000000"))
    turn = math.radians(90)  # a quarter turn counterclockwise about (1, 1), then up by 2
    a, b, c, d = math.cos(turn), math.sin(turn), -math.sin(turn), math.cos(turn)
    e, f = 1 - (a * 1 + c * 1), 1 - (b * 1 + d * 1) + 2
    matrix = frame.matrix((a, b, c, d, e, f))
    # (2, 1) in units turns to (1, 2), then rises to (1, 4); in pixels:
    assert apply(matrix, 960 + 2 * 120, 540 - 120) == pytest.approx((960 + 120, 540 - 4 * 120))


def test_numbers_are_short_and_stable() -> None:
    assert [num(v) for v in (1.0, 2.5, 1 / 3, -0.0001, 120.0004)] == [
        "1",
        "2.5",
        "0.333",
        "0",
        "120",
    ]


# The backend


def test_it_draws_everything_but_tex_itself() -> None:
    assert Capability.MATH not in SvgBackend.capabilities
    assert Capability.CUBIC in SvgBackend.capabilities


def test_it_writes_frame_svg_and_a_png_of_the_output_size(
    make_lir: Any, group: Any, line: dict[str, Any], tmp_path: Path
) -> None:
    pytest.importorskip("cairosvg")
    rendered = SvgBackend().render(make_lir(group("a", line)), tmp_path)
    assert [p.name for p in rendered.files] == ["frame.svg", "frame.png"]
    assert rendered.issues == ()
    assert png_size(tmp_path / "frame.png") == (1920, 1080)


def test_the_png_can_be_switched_off(
    make_lir: Any, group: Any, line: dict[str, Any], tmp_path: Path
) -> None:
    rendered = SvgBackend({"png": False}).render(make_lir(group("a", line)), tmp_path)
    assert [p.name for p in rendered.files] == ["frame.svg"]


def test_without_cairosvg_the_svg_is_kept_and_the_missing_tool_is_reported(
    make_lir: Any,
    group: Any,
    line: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(*args: object) -> None:
        raise ImportError("No module named 'cairosvg'")

    monkeypatch.setattr("irpipe.backends.svg.svg_to_png", missing)
    rendered = SvgBackend().render(make_lir(group("a", line)), tmp_path)
    assert [p.name for p in rendered.files] == ["frame.svg"]
    (issue,) = rendered.issues
    assert (issue.code, issue.origin) == ("E-ENVIRONMENT", "environment")
    assert issue.hint is not None and "svg" in issue.hint
