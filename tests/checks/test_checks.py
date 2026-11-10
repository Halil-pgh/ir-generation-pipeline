"""Each check finds what it is for, and stays quiet otherwise.

Pictures are written as IR and drawn the way the pipeline draws them
(normalize, measure with the "fixed" measurer, place, resolve), so the
checks see a real LIR. With "fixed", a text of n glyphs at s px is
n * s * 0.55 / 120 units wide and s / 120 tall; 42 px is the body size.
"""

import shutil
from collections.abc import Callable
from typing import Any

import pytest

from irpipe.checks import Check, Picture
from irpipe.checks.colors import SimilarColors
from irpipe.checks.contrast import Contrast
from irpipe.checks.fill_overlap import FillOverlap
from irpipe.checks.frame import Offscreen
from irpipe.checks.glyphs import Glyphs
from irpipe.checks.group_opacity import GroupOpacity
from irpipe.checks.safe_area import SafeArea
from irpipe.checks.subtitle import Subtitle
from irpipe.checks.text_crossed import TextCrossed
from irpipe.checks.text_overlap import TextOverlap
from irpipe.checks.text_size import TextSize
from irpipe.core import Issue
from irpipe.frontend.measure import measure
from irpipe.frontend.normalize import normalize
from irpipe.frontend.place import place
from irpipe.frontend.resolve import Resolver
from irpipe.metrics.fixed import FixedMetrics
from irpipe.schema.ir import IRDocument

type Make = Callable[..., IRDocument]


def picture(document: IRDocument) -> Picture:
    normal = normalize(document)
    measured, _ = measure(normal, FixedMetrics())
    assert measured is not None
    placed, problems = place(normal, measured)
    assert placed is not None, problems
    return Picture(Resolver(placed, measured).resolve(), normal)


def found(check: Check, document: IRDocument) -> list[Issue]:
    return list(check.check(picture(document)))


def text(oid: str, at: list[float] | str, content: str = "word", **fields: Any) -> dict[str, Any]:
    return {"id": oid, "type": "text", "text": content, "at": at, **fields}


def line(oid: str, start: list[float], end: list[float], **fields: Any) -> dict[str, Any]:
    return {"id": oid, "type": "line", "start": start, "end": end, **fields}


def disc(oid: str, center: list[float], radius: float, **fields: Any) -> dict[str, Any]:
    return {"id": oid, "type": "circle", "center": center, "radius": radius, **fields}


# The frame (16 x 9 units) and the safe area ([-7.6, -4.1, 7.6, 4.1])


def test_offscreen_says_which_edge_and_how_far(document: Make) -> None:
    (issue,) = found(Offscreen(), document([line("l", [-9, 0], [0, 0], stroke_width=12)]))
    assert (issue.code, issue.path, issue.objects) == ("W-OFFSCREEN", "objects[0]", ("l",))
    assert issue.message == "'l' reaches 1.05 past the left edge of the frame"  # 1 + half of 0.1


def test_a_line_ending_on_the_edge_is_not_offscreen(document: Make) -> None:
    assert found(Offscreen(), document([line("l", [8, -1], [8, 1], color="none")])) == []


def test_safe_area_reports_what_the_platform_may_cover(document: Make) -> None:
    (issue,) = found(SafeArea(), document([disc("c", [0, 3.8], 0.5)]))
    assert issue.message.startswith("'c' reaches 0.2")
    assert "top edge of the safe area" in issue.message
    assert found(SafeArea(), document([disc("c", [0, 0], 0.5)])) == []


def test_drawing_in_the_subtitle_band_is_an_error(ir: Callable[..., dict[str, Any]]) -> None:
    data = ir([disc("c", [0, -3.6], 0.5), disc("ok", [0, 0], 0.5)])
    data["frame"]["subtitle"] = {"mode": "reserve", "lines": 2, "band": [-7.6, -4.4, 7.6, -3.4]}
    (issue,) = found(Subtitle(), IRDocument.model_validate(data))
    assert (issue.code, issue.severity.value, issue.objects) == ("E-SUBTITLE", "error", ("c",))


def test_without_a_band_there_is_nothing_to_keep_clear(document: Make) -> None:
    assert found(Subtitle(), document([disc("c", [0, -3.9], 0.5)])) == []


# Texts


def test_texts_on_top_of_each_other(document: Make) -> None:
    objects = [text("a", [0, 0]), text("b", [0.5, 0.1]), text("far", [0, 2])]
    (issue,) = found(TextOverlap(), document(objects))
    assert (issue.code, issue.objects, issue.path) == ("W-TEXT-OVERLAP", ("a", "b"), "objects[1]")


def test_a_line_through_a_text_whatever_relates_them(document: Make) -> None:
    objects = [line("l", [-3, 0], [3, 0]), text("t", "l.mid")]  # set on its own line's middle
    (issue,) = found(TextCrossed(), document(objects))
    assert (issue.code, issue.objects) == ("W-TEXT-CROSSED", ("t", "l"))
    beside = [line("l", [-3, 0], [3, 0]), text("t", "l.mid", dir="up")]
    assert found(TextCrossed(), document(beside)) == []


def test_contrast_is_against_the_color_actually_behind(document: Make) -> None:
    panel = {"id": "p", "type": "rect", "center": [0, 0], "width": 4, "height": 2,
             "fill": "#FFFFFF", "color": "none"}  # fmt: skip
    (issue,) = found(Contrast(), document([panel, text("t", [0, 0])]))  # white text on white
    assert issue.code == "W-LOW-CONTRAST"
    assert issue.message.startswith("'t' has contrast 1.0:1 against what is behind it")
    assert found(Contrast(), document([text("t", [0, 0])])) == []  # white on the dark background


def test_a_faded_text_loses_contrast_and_large_text_needs_less(document: Make) -> None:
    grey = {"id": "t", "type": "text", "text": "x", "at": [0, 0], "color": "#5A6070"}
    (issue,) = found(Contrast(), document([grey]))  # about 3:1 on #0E1117
    assert "it needs 4.5:1" in issue.message
    assert found(Contrast(), document([{**grey, "size": "title"}])) == []  # 64 px is large


def test_text_size_has_a_floor(document: Make) -> None:
    (issue,) = found(TextSize(), document([text("t", [0, 0], size=20), text("u", [0, 1])]))
    assert (issue.code, issue.objects) == ("W-SMALL-TEXT", ("t",))
    assert found(TextSize({"min_size": 18}), document([text("t", [0, 0], size=20)])) == []


# Colors and fills


def test_colors_too_alike_are_reported_with_their_users(document: Make) -> None:
    objects = [
        line("p", [0, 0], [1, 0], color="#FFD43B"),
        line("q", [0, 1], [1, 1], color="#FFD040"),
        line("r", [0, 2], [1, 2], color="#FFD43B"),
    ]
    (issue,) = found(SimilarColors(), document(objects))
    assert issue.code == "W-SIMILAR-COLORS"
    assert set(issue.objects) == {"p", "q", "r"}
    assert found(SimilarColors(), document(objects[::2])) == []  # one color, one concept


def test_fills_that_partly_overlap_by_accident(document: Make) -> None:
    a, b = disc("A", [-0.5, 0], 1, fill="a"), disc("B", [0.5, 0], 1, fill="b")
    (issue,) = found(FillOverlap(), document([a, b]))
    assert (issue.code, issue.objects) == ("W-FILL-OVERLAP", ("A", "B"))
    assert '{"intersection": ["A", "B"]}' in (issue.hint or "")


def test_layering_grouping_and_regions_are_not_accidents(document: Make) -> None:
    panel = disc("panel", [0, 0], 3, fill="a")
    dot = disc("dot", [0, 0], 0.2, fill="b")
    assert found(FillOverlap(), document([panel, dot])) == []  # one wholly inside the other
    a, b = disc("A", [-0.5, 0], 1, fill="a"), disc("B", [0.5, 0], 1, fill="b")
    group = {"id": "g", "type": "group", "children": ["A", "B"]}
    assert found(FillOverlap(), document([a, b, group])) == []
    # Either but not both of A and B partly overlaps A, but is built from it, so it is meant.
    either = {"id": "X", "type": "region", "shape": {"xor": ["A", "B"]}, "fill": "b"}
    assert found(FillOverlap(), document([a, either], defs=[{**b, "fill": None}])) == []
    stranger = {**either, "shape": {"xor": ["C", "B"]}}
    c = disc("C", [-0.5, 0], 1)
    (issue,) = found(FillOverlap(), document([a, stranger], defs=[c, {**b, "fill": None}]))
    assert issue.objects == ("A", "X")


def test_a_faded_group_whose_children_overlap(document: Make) -> None:
    a, b = disc("A", [-0.5, 0], 1, fill="a"), disc("B", [0.5, 0], 1, fill="b")
    faded = {"id": "g", "type": "group", "children": ["A", "B"], "opacity": 0.5}
    (issue,) = found(GroupOpacity(), document([a, b, faded]))
    assert (issue.code, issue.objects, issue.path) == (
        "W-GROUP-OPACITY",
        ("g", "A", "B"),
        "objects[2]",
    )
    apart = [disc("A", [-3, 0], 1, fill="a"), b, faded]
    assert found(GroupOpacity(), document(apart)) == []


# Glyphs


@pytest.mark.skipif(shutil.which("fc-match") is None, reason="fontconfig is not installed")
def test_a_character_the_font_lacks(document: Make) -> None:
    objects = [text("t", [0, 0], content="x \U000f0000"), {"id": "m", "type": "math", "tex": "x",
               "at": [0, 1]}]  # fmt: skip
    (issue,) = found(Glyphs(), document(objects))
    assert (issue.code, issue.objects) == ("W-MISSING-GLYPH", ("t",))
    assert "U+F0000" in issue.message


# Options


def test_a_misspelled_option_is_refused() -> None:
    with pytest.raises(Exception, match="check 'text_size' options: min_szie"):
        TextSize({"min_szie": 10})
