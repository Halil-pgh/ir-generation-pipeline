"""lower: what a backend cannot draw is rewritten with simpler features, or reported in IR terms."""

import math
from itertools import combinations
from typing import Any

import pytest
from shapely.geometry import LineString

from irpipe.backends.base import Capability, features_used
from irpipe.frontend import shapes
from irpipe.frontend.geometry import areas, curves
from irpipe.frontend.lower import TOLERANCE, lower
from irpipe.schema import lir

EVERYTHING = frozenset(Capability)
CIRCLE = shapes.ellipse((0, 0), 2, 2)
SMALL = shapes.ellipse((0, 0), 1, 1)
WHITE = {"color": "#FFFFFF", "width": 4}
GLYPH = shapes.polyline(((0, 0), (0.1, 0), (0, 0.1)), closed=True)
FORMULA: dict[str, Any] = {
    "type": "math",
    "tex": "x",
    "size": 42,
    "color": "#FFFFFF",
    "opacity": 0.5,
    "at": [0, 0],
    "anchor": "left_baseline",
    "box": [0, -0.1, 0.2, 0.3],
    "baseline": 0,
}
TEXT: dict[str, Any] = {
    "type": "text",
    "text": "hi",
    "font": "Inter",
    "size": 42,
    "color": "#FFFFFF",
    "at": [0, 0],
    "anchor": "left_baseline",
    "box": [0, -0.1, 0.4, 0.3],
    "baseline": 0,
}


def path(*subpaths: lir.Subpath, **paint: Any) -> dict[str, Any]:
    return {"type": "path", "subpaths": [s.model_dump() for s in subpaths], **paint}


def group(gid: str, *children: dict[str, Any], **fields: Any) -> dict[str, Any]:
    return {"type": "group", "id": gid, "source": f"objects[{gid}]", "children": list(children),
            **fields}  # fmt: skip


def drawing(*groups: dict[str, Any]) -> lir.LIRDocument:
    canvas = {"units": [16, 9], "pixels": [1920, 1080], "background": "#0E1117"}
    return lir.LIRDocument.model_validate({"canvas": canvas, "items": list(groups)})


def only(lowered: lir.LIRDocument) -> list[Any]:
    """The primitives of the one group."""
    (item,) = lowered.items
    return list(item.children)


def stray(first: tuple[lir.Subpath, ...], second: tuple[lir.Subpath, ...]) -> float:
    """How far apart two outlines get (the Hausdorff distance of their polylines)."""
    a = LineString([p for s in first for p in curves.flatten(s, 256)])
    b = LineString([p for s in second for p in curves.flatten(s, 256)])
    return float(a.hausdorff_distance(b))


def kinds(subpaths: tuple[lir.Subpath, ...]) -> set[str]:
    return {type(segment).__name__ for s in subpaths for segment in s.segments}


# Nothing to lower


def test_a_backend_that_can_draw_everything_gets_the_lir_unchanged() -> None:
    source = drawing(
        group("c", path(CIRCLE, stroke={**WHITE, "dash": [8, 4]}, fill={"color": "#FFFFFF",
                                                                         "rule": "evenodd"})),
        group("f", FORMULA, transform=[0, 1, -1, 0, 0, 0]),
    )  # fmt: skip
    lowered, problems = lower(source, EVERYTHING)
    assert (lowered, problems) == (source, [])


# Curves


def test_cubics_become_quadratics_within_the_tolerance() -> None:
    lowered, _ = lower(drawing(group("c", path(CIRCLE, stroke=WHITE))), {Capability.QUADRATIC})
    (item,) = only(lowered)
    assert kinds(item.subpaths) == {"QuadTo"}
    assert stray(item.subpaths, (CIRCLE,)) < TOLERANCE


def test_without_curves_everything_is_straight_within_the_tolerance() -> None:
    lowered, _ = lower(drawing(group("c", path(CIRCLE, stroke=WHITE))), set())
    (item,) = only(lowered)
    assert kinds(item.subpaths) == {"LineTo"}
    assert stray(item.subpaths, (CIRCLE,)) < TOLERANCE


def test_quadratics_become_cubics_exactly() -> None:
    bow = lir.Subpath(start=(0, 0), segments=(lir.QuadTo(quad=((1, 2), (2, 0))),))
    lowered, _ = lower(drawing(group("q", path(bow, stroke=WHITE))), {Capability.CUBIC})
    ((piece,),) = [curves.pieces(s) for s in only(lowered)[0].subpaths]
    assert len(piece) == 4
    for t in (0.1, 0.5, 0.9):
        assert curves.point(piece, t) == pytest.approx(curves.point(((0, 0), (1, 2), (2, 0)), t))


# Dashes


def test_dashes_become_one_path_each_and_the_fill_stays_whole() -> None:
    line = shapes.polyline(((0, 0), (4, 0)))
    dashed = path(line, stroke={**WHITE, "dash": [120, 120]})  # one unit on, one off
    (item,) = only(lower(drawing(group("l", dashed)), set())[0])
    assert item.stroke.dash is None
    ends = [(s.start, s.segments[-1].line) for s in item.subpaths]
    assert ends == [((0, 0), (1, 0)), ((2, 0), (3, 0))]
    square = shapes.rect((1, 1), 2, 2, 0)
    boxed = path(square, stroke={**WHITE, "dash": [120]}, fill={"color": "#FFFFFF"},
                 hint={"shape": "rect", "center": [1, 1], "width": 2, "height": 2})  # fmt: skip
    fill, stroke = only(lower(drawing(group("r", boxed)), set())[0])
    assert (fill.stroke, fill.hint is not None, stroke.fill) == (None, True, None)
    assert len(stroke.subpaths) == 4  # 8 units round, an odd pattern repeated: 1 on, 1 off
    assert curves.subpaths_length(stroke.subpaths) == pytest.approx(4)


def test_dashes_run_on_round_curves() -> None:
    dashed = path(CIRCLE, stroke={**WHITE, "dash": [60, 60]})
    (item,) = only(lower(drawing(group("c", dashed)), EVERYTHING - {Capability.DASH})[0])
    assert kinds(item.subpaths) == {"CubicTo"}
    # 4 pi units round: 12 whole patterns of half a unit on, half off, and 0.57 more of one.
    assert curves.subpaths_length(item.subpaths) == pytest.approx(6.5, rel=1e-3)


# Fill rules


def test_an_even_odd_hole_becomes_a_nonzero_hole_keeping_its_curves() -> None:
    ring = path(CIRCLE, SMALL, fill={"color": "#FFFFFF", "rule": "evenodd"})
    (item,) = only(lower(drawing(group("r", ring)), EVERYTHING - {Capability.EVENODD})[0])
    assert item.fill.rule == "nonzero"
    assert kinds(item.subpaths) == {"CubicTo"}
    assert areas.area(item.subpaths, "nonzero").area == pytest.approx(3 * math.pi, rel=1e-3)


def test_crossing_outlines_are_recomputed() -> None:
    other = shapes.ellipse((2, 0), 2, 2)
    both = path(CIRCLE, other, fill={"color": "#FFFFFF", "rule": "evenodd"})
    (item,) = only(lower(drawing(group("x", both)), EVERYTHING - {Capability.EVENODD})[0])
    expected = areas.area((CIRCLE, other), "evenodd").area
    assert areas.area(item.subpaths, "nonzero").area == pytest.approx(expected, rel=1e-3)


# Group transforms


def test_group_transforms_are_applied_to_the_children() -> None:
    line = path(shapes.polyline(((0, 0), (1, 0))), stroke={**WHITE, "dash": [8, 4]})
    inner = group("l", line, transform=[2, 0, 0, 2, 0, 0])
    outer = group("g", inner, transform=[0, 1, -1, 0, 1, 0])  # a quarter turn, then right by 1
    lowered, problems = lower(drawing(outer), EVERYTHING - {Capability.TRANSFORM})
    assert problems == []
    (g,) = lowered.items
    (child,) = g.children
    assert isinstance(child, lir.Group)
    (item,) = child.children
    assert isinstance(item, lir.PathItem) and item.stroke is not None
    assert (g.transform, child.transform) == (lir.IDENTITY, lir.IDENTITY)
    (piece,) = item.subpaths
    (segment,) = piece.segments
    assert isinstance(segment, lir.LineTo)
    assert piece.start == pytest.approx((1, 0))
    assert segment.line == pytest.approx((1, 2))
    assert (item.stroke.width, item.stroke.dash) == (8, (16, 8))


def test_a_text_follows_a_shift_and_an_even_scale() -> None:
    moved = group("t", TEXT, transform=[2, 0, 0, 2, 1, 1])
    (item,) = only(lower(drawing(moved), EVERYTHING - {Capability.TRANSFORM})[0])
    assert (item.at, item.size, item.baseline) == ((1, 1), 84, 1)
    assert item.box == pytest.approx((1, 0.8, 1.8, 1.6))


def test_a_turned_text_cannot_be_lowered_and_is_named_in_ir_terms() -> None:
    turned = group("t", TEXT, transform=[0, 1, -1, 0, 0, 0])
    lowered, problems = lower(drawing(turned), EVERYTHING - {Capability.TRANSFORM})
    (issue,) = problems
    assert (issue.code, issue.objects, issue.path) == ("E-CAPABILITY", ("t",), "objects[t]")
    assert "svg" not in issue.message and "backend" not in issue.message
    assert only(lowered) == []


def test_a_turned_formula_is_drawn_from_its_outlines() -> None:
    turned = group("f", {**FORMULA, "glyphs": [GLYPH.model_dump()]}, transform=[0, 1, -1, 0, 0, 0])
    lowered, problems = lower(drawing(turned), EVERYTHING - {Capability.TRANSFORM})
    assert problems == []
    (item,) = only(lowered)
    assert isinstance(item, lir.PathItem)
    first = item.subpaths[0].segments[0]
    assert isinstance(first, lir.LineTo)
    assert first.line == pytest.approx((0, 0.1))  # (0.1, 0) turned a quarter


# Formulas, texts and images


def test_formulas_become_their_outlines_where_tex_cannot_be_set() -> None:
    with_glyphs = group("f", {**FORMULA, "glyphs": [GLYPH.model_dump()]})
    (item,) = only(lower(drawing(with_glyphs), EVERYTHING - {Capability.MATH})[0])
    assert isinstance(item, lir.PathItem) and item.fill is not None
    assert (item.fill.color, item.fill.opacity, item.stroke) == ("#FFFFFF", 0.5, None)
    assert item.subpaths == (GLYPH,)


def test_a_formula_without_outlines_is_the_environments_problem() -> None:
    lowered, problems = lower(drawing(group("f", FORMULA)), EVERYTHING - {Capability.MATH})
    (issue,) = problems
    assert (issue.code, issue.origin, issue.objects) == ("E-ENVIRONMENT", "environment", ("f",))
    assert only(lowered) == []
    assert "pango" in (issue.hint or "")


def test_texts_where_texts_cannot_be_drawn() -> None:
    _, problems = lower(drawing(group("t", TEXT)), EVERYTHING - {Capability.TEXT})
    (issue,) = problems
    assert (issue.code, issue.origin) == ("E-CAPABILITY", "capability")
    assert "\\text{" in (issue.hint or "")


def test_images_cannot_become_paths() -> None:
    image = {"type": "image", "src": "a.png", "box": [0, 0, 1, 1]}
    _, problems = lower(drawing(group("i", image)), EVERYTHING - {Capability.IMAGE})
    assert [p.code for p in problems] == ["E-CAPABILITY"]


# What is left


RICH = drawing(
    group("c", path(CIRCLE, SMALL, stroke={**WHITE, "dash": [8, 4]},
                    fill={"color": "#FFFFFF", "rule": "evenodd"})),
    group("q", path(lir.Subpath(start=(0, 0), segments=(lir.QuadTo(quad=((1, 1), (2, 0))),)),
                    stroke=WHITE), transform=[2, 0, 0, 2, 0, 0]),
    group("f", {**FORMULA, "glyphs": [CIRCLE.model_dump()]}, transform=[0, 1, -1, 0, 0, 0]),
    group("t", TEXT),
)  # fmt: skip
OPTIONAL = [c for c in Capability if c is not Capability.TEXT]


@pytest.mark.parametrize(
    "missing",
    [set(pair) for pair in combinations(OPTIONAL, 2)] + [set(OPTIONAL)],
    ids=lambda missing: "-".join(sorted(missing)),
)
def test_after_lowering_only_what_the_backend_lists_is_left(missing: set[Capability]) -> None:
    can = EVERYTHING - missing
    lowered, problems = lower(RICH, can)
    assert problems == []
    assert set(features_used(lowered)) <= can
