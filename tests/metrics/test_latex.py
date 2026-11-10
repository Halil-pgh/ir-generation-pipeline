"""Typesetting a formula with latex and dvisvgm: outlines, box, and LaTeX's own errors."""

import shutil

import pytest

from irpipe.metrics.latex import MissingToolError, TexError, typeset

needs_tex = pytest.mark.skipif(
    shutil.which("latex") is None or shutil.which("dvisvgm") is None,
    reason="needs latex and dvisvgm",
)


@needs_tex
def test_the_outlines_fill_the_box_and_sit_on_the_baseline() -> None:
    outline = typeset(r"\frac{a}{b} + x_1", math_font="latin-modern")
    xs = [
        p[0]
        for s in outline.subpaths
        for p in [s.start, *(q for _, pts in s.segments for q in pts)]
    ]
    ys = [
        p[1]
        for s in outline.subpaths
        for p in [s.start, *(q for _, pts in s.segments for q in pts)]
    ]
    assert min(xs) == pytest.approx(0, abs=0.01)
    assert max(xs) == pytest.approx(outline.width, abs=0.01)
    assert max(ys) == pytest.approx(outline.ascent, abs=0.01)
    assert min(ys) == pytest.approx(-outline.descent, abs=0.01)


@needs_tex
def test_a_fraction_bar_is_an_outline_too() -> None:
    plain = typeset("ab", math_font="latin-modern")
    stacked = typeset(r"\frac{a}{b}", math_font="latin-modern")
    assert len(stacked.subpaths) > len(plain.subpaths)


@needs_tex
@pytest.mark.parametrize(
    ("tex", "message"),
    [
        (r"\fraq{1}{2}", r"Undefined control sequence, after: \fraq"),
        (r"\frac{1}{2", r"File ended while scanning use of \frac"),
        ("x^", "Missing { inserted, after: x^"),
    ],
)
def test_a_tex_mistake_comes_back_in_latexs_words_without_the_template(
    tex: str, message: str
) -> None:
    with pytest.raises(TexError) as caught:
        typeset(tex, math_font="latin-modern")
    assert str(caught.value) == message
    assert "displaystyle" not in str(caught.value)


def test_an_unknown_math_font_is_refused() -> None:
    with pytest.raises(MissingToolError, match="math font 'comic-math' is not supported"):
        typeset("x", math_font="comic-math")


def test_without_latex_the_tool_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda tool: None)
    with pytest.raises(MissingToolError, match="latex is not installed"):
        typeset("x", math_font="latin-modern")
