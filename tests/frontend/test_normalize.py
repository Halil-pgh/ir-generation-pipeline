"""normalize: every object's paint written out, and colors that have no name reported."""

import json
from collections.abc import Callable
from typing import Any

import pytest

from irpipe.artifacts import IR, IR_SOURCE
from irpipe.core import Pipeline, PipelineConfigError, Report, Status
from irpipe.frontend.normalize import Normalize, normalize, undeclared_colors
from irpipe.frontend.resolve import Resolve
from irpipe.frontend.validate import Validate
from irpipe.schema.ir import Circle, IRDocument, Line, Text, header_hash

type Make = Callable[..., IRDocument]

CIRCLE = {"id": "c", "type": "circle", "center": [0, 0], "radius": 1}
LINE = {"id": "l", "type": "line", "start": [0, 0], "end": [1, 1]}
TEXT = {"id": "t", "type": "text", "text": "x", "at": [0, 0]}


def first(document: IRDocument) -> Any:
    return normalize(document).objects[0]


# Paint written out


def test_every_paint_field_is_written_out_and_the_classes_are_gone(document: Make) -> None:
    circle = first(document([{**CIRCLE, "style": "dashed", "fill": "a"}]))
    assert isinstance(circle, Circle)
    assert circle.style is None
    assert (circle.color, circle.fill) == ("#FFFFFF", "#FFD43B")
    assert (circle.stroke_width, circle.dash) == (3, (14, 10))  # from the class
    assert (circle.opacity, circle.fill_opacity) == (1, 1)


def test_a_text_gets_its_size_in_reference_pixels(document: Make) -> None:
    text = first(document([{**TEXT, "size": "caption"}]))
    assert isinstance(text, Text)
    assert (text.size, text.weight, text.italic) == (34, "regular", False)


def test_no_paint_stays_none(document: Make) -> None:
    circle = first(document([{**CIRCLE, "color": "none"}]))
    assert (circle.color, circle.fill) == ("none", "none")


def test_the_theme_gives_texts_and_lines_their_own_colors(document: Make) -> None:
    theme = {"text": "#FF0000", "line": [0, 255, 0], "stroke_width": 6}
    doc = document([TEXT, LINE], theme=theme)
    text, line = normalize(doc).objects
    assert isinstance(text, Text) and isinstance(line, Line)
    assert (text.color, line.color, line.stroke_width) == ("#FF0000", "#00FF00", 6)


def test_a_theme_color_left_out_contrasts_with_the_background(ir: Callable[..., Any]) -> None:
    data = ir([LINE], theme={"text": "#FF0000"})
    data["frame"]["background"] = "#FAFAFA"
    (line,) = normalize(IRDocument.model_validate(data)).objects
    assert isinstance(line, Line)
    assert line.color == "#000000"


def test_the_normalized_ir_is_still_a_valid_ir_with_the_same_header(document: Make) -> None:
    doc = document([{**CIRCLE, "style": "boxed"}, {**TEXT, "size": "label"}, LINE])
    normal = normalize(doc)
    again = IRDocument.model_validate(json.loads(normal.model_dump_json()))
    assert again == normal
    assert header_hash(normal.header) == header_hash(doc.header)


# Colors without a name


@pytest.mark.parametrize(
    ("objects", "found"),
    [
        ([{**CIRCLE, "fill": "#ffffff"}], [("objects[0].fill", "c")]),
        ([{**LINE, "color": [255, 0, 0]}], [("objects[0].color", "l")]),
        ([CIRCLE, {**TEXT, "color": "#00FF00"}], [("objects[1].color", "t")]),
    ],
)
def test_a_literal_color_is_reported_where_it_is_written(
    document: Make, objects: list[dict[str, Any]], found: list[tuple[str, str]]
) -> None:
    issues = list(undeclared_colors(document(objects)))
    assert [(i.path, i.objects[0]) for i in issues] == found
    assert all(i.code == "W-UNDECLARED-COLOR" for i in issues)


def test_the_hint_offers_a_name_for_the_color(document: Make) -> None:
    (issue,) = undeclared_colors(document([{**LINE, "color": [255, 0, 0]}]))
    assert issue.hint == 'name it in extra_colors (such as "ink": "#FF0000") and use the name here'


def test_named_colors_none_and_the_headers_styles_are_fine(document: Make) -> None:
    objects = [
        {**CIRCLE, "fill": "a", "color": "none"},
        {**LINE, "color": "AB", "style": "glow"},
    ]
    doc = document(
        objects,
        extra_colors={"AB": {"mix": ["a", "b"]}},
        styles={"glow": {"color": "#FFFFFF"}},
    )
    assert list(undeclared_colors(doc)) == []


def run(text: str) -> Report:
    pipeline = Pipeline([Validate(), Normalize()], inputs=[IR_SOURCE])
    result = pipeline.run({IR_SOURCE: text})
    return Report.build(result.issues, allows=result.get(IR).allow, stopped_at=result.stopped_at)


def test_a_literal_color_on_purpose_can_be_allowed(ir_text: Callable[..., str]) -> None:
    circle = {**CIRCLE, "fill": "#FFFFFF"}
    assert run(ir_text([circle])).status is Status.NOT_READY
    allow = {
        "code": "W-UNDECLARED-COLOR",
        "objects": ["c"],
        "reason": "plain white is the paper of this sketch",
    }
    assert run(ir_text([circle], allow=[allow])).status is Status.READY


# Plug and play


def test_without_normalize_resolve_has_nothing_to_draw_from() -> None:
    with pytest.raises(PipelineConfigError, match="'resolve' requires artifact 'ir_normal'"):
        Pipeline([Validate(), Resolve()], inputs=[IR_SOURCE])
