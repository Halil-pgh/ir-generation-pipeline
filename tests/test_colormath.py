"""colormath: WCAG luminance and contrast, blending, Lab and CIEDE2000."""

import pytest

from irpipe import colormath


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        # Published test pairs for CIEDE2000 (Sharma, Wu and Dalal, 2005).
        ((50, 2.6772, -79.7751), (50, 0, -82.7485), 2.0425),
        ((50, 0, 0), (50, -1, 2), 2.3669),
        ((50, 2.5, 0), (73, 25, -18), 27.1492),
        ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ],
)
def test_ciede2000_matches_the_published_pairs(
    first: tuple[float, float, float], second: tuple[float, float, float], expected: float
) -> None:
    assert colormath.delta_e(first, second) == pytest.approx(expected, abs=1e-4)


def test_contrast_runs_from_1_to_21_as_wcag_defines_it() -> None:
    white, black = colormath.rgb("#FFFFFF"), colormath.rgb("#000000")
    assert colormath.contrast(white, black) == pytest.approx(21)
    assert colormath.contrast(black, white) == pytest.approx(21)
    assert colormath.contrast(colormath.rgb("#777777"), white) == pytest.approx(4.48, abs=0.01)


def test_blending_and_hex() -> None:
    mixed = colormath.blend((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), 0.25)
    assert colormath.hex_of(mixed) == "#4000BF"
    assert colormath.rgb("#4000BF") == pytest.approx((64 / 255, 0, 191 / 255))


def test_lab_of_white_and_black() -> None:
    assert colormath.lab((1.0, 1.0, 1.0)) == pytest.approx((100, 0, 0), abs=0.01)
    assert colormath.lab((0.0, 0.0, 0.0)) == pytest.approx((0, 0, 0), abs=0.01)
