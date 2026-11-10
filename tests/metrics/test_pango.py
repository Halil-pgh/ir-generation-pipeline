"""The pango measurer: Pango's metrics for text, LaTeX for formulas."""

import shutil

import pytest

pytest.importorskip("pangocffi")

from irpipe.metrics.pango import PangoMetrics


@pytest.fixture(scope="module")
def pango() -> PangoMetrics:
    metrics = PangoMetrics()
    if metrics.missing_fonts(["DejaVu Sans"]):
        pytest.skip("needs the DejaVu Sans font")
    return metrics


def measure(
    pango: PangoMetrics, text: str, size: float = 40, weight: str = "regular"
) -> tuple[float, float, float]:
    box = pango.text(text, font="DejaVu Sans", size=size, weight=weight, italic=False)  # type: ignore[arg-type]
    return box.width, box.ascent, box.descent


def test_twice_the_size_is_exactly_twice_as_big(pango: PangoMetrics) -> None:
    small, large = measure(pango, "Projection", 40), measure(pango, "Projection", 80)
    assert large == pytest.approx(tuple(2 * v for v in small), rel=1e-6)


def test_the_box_is_the_fonts_not_the_letters(pango: PangoMetrics) -> None:
    _, ascent_x, descent_x = measure(pango, "x")
    _, ascent_g, descent_g = measure(pango, "Åg")
    assert (ascent_x, descent_x) == (ascent_g, descent_g)  # baselines stay steady


def test_bold_is_wider(pango: PangoMetrics) -> None:
    assert measure(pango, "word", weight="bold")[0] > measure(pango, "word")[0]


def test_a_font_that_is_not_installed_is_named(pango: PangoMetrics) -> None:
    assert pango.missing_fonts(["DejaVu Sans", "No Such Font Xyz"]) == ["No Such Font Xyz"]


@pytest.mark.skipif(shutil.which("latex") is None, reason="needs latex")
def test_a_formula_scales_with_its_size(pango: PangoMetrics) -> None:
    small = pango.math("x^2", math_font="latin-modern", size=40)
    large = pango.math("x^2", math_font="latin-modern", size=80)
    assert large.width == pytest.approx(2 * small.width)
    assert large.outlines[0].start == pytest.approx(tuple(2 * v for v in small.outlines[0].start))
