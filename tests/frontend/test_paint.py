"""The paint cascade and color names."""

from collections.abc import Callable

import pytest

from irpipe.frontend.paint import PaintResolver, foreground_for, to_hex
from irpipe.schema.ir import IRDocument

LINE = {"id": "l", "type": "line", "start": [0, 0], "end": [1, 1]}

type Make = Callable[..., IRDocument]


def test_the_cascade_is_theme_then_classes_then_the_object(document: Make) -> None:
    doc = document(
        [{**LINE, "style": ["dashed", "thin"], "dash": [2, 2]}],
        styles={"dashed": {"dash": [14, 10], "stroke_width": 3}, "thin": {"stroke_width": 1}},
    )
    paint = PaintResolver(doc).paint(doc.objects[0])
    assert paint.stroke_width == 1  # the later class wins over the earlier one
    assert paint.dash == (2, 2)  # the object wins over both
    assert paint.color == "#FFFFFF"  # nobody set it: the theme
    assert paint.fill is None  # the theme fills nothing


@pytest.mark.parametrize(
    ("background", "foreground"),
    [("#0E1117", "#FFFFFF"), ("#FAFAFA", "#000000"), ((40, 40, 140), "#FFFFFF")],
)
def test_the_theme_color_contrasts_with_the_background(
    background: str | tuple[int, int, int], foreground: str
) -> None:
    assert foreground_for(background) == foreground


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("a", "#FFD43B"),
        ("b", "#58C4DD"),
        ("#ffd43b", "#FFD43B"),
        ((1, 2, 3), "#010203"),
        ("AB", "#ACCC8C"),  # (255 + 88) / 2 = 171.5, rounded to 172 = 0xAC
        ("none", None),
    ],
)
def test_color_names_become_hex(document: Make, ref: str, expected: str | None) -> None:
    doc = document([LINE], extra_colors={"AB": {"mix": ["a", "b"]}})
    assert PaintResolver(doc).color(ref) == expected


def test_a_text_role_becomes_its_size(document: Make) -> None:
    resolver = PaintResolver(document([LINE]))
    assert (resolver.size("caption"), resolver.size(27)) == (34, 27)


def test_hex_is_upper_case() -> None:
    assert to_hex("#0e1117") == "#0E1117"
