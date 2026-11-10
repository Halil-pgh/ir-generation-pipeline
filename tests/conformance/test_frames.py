"""Every aspect and resolution: the backends agree, and widths are reference pixels.

A frame is 9 units on its short side and a reference pixel is 1/1080 of
it, whatever the aspect and the output size (analysis §3). The same scene
is drawn on several frames; both backends must agree on each, and a
4 reference px line must be 4 px thick at 1080 and 8 px at 2160.
"""

from typing import Any

import numpy as np
import pytest

pytestmark = pytest.mark.manim

FRAMES = {
    "16:9": ([16, 9], [1920, 1080]),
    "9:16": ([9, 16], [1080, 1920]),
    "1:1": ([9, 9], [1080, 1080]),
    "4:5": ([9, 11.25], [1080, 1350]),
    "21:9": ([21, 9], [2520, 1080]),
    "16:9 4K": ([16, 9], [3840, 2160]),
}


def scene(group: Any) -> list[dict[str, Any]]:
    """A 4 px line across the middle, a filled ring and a dashed square, inside 9 x 9 units."""
    k = 0.5522847498

    def circle(r: float) -> dict[str, Any]:
        s = r * k
        return {
            "start": [r, 1.5],
            "segments": [
                {"cubic": [[r, 1.5 + s], [s, 1.5 + r], [0, 1.5 + r]]},
                {"cubic": [[-s, 1.5 + r], [-r, 1.5 + s], [-r, 1.5]]},
                {"cubic": [[-r, 1.5 - s], [-s, 1.5 - r], [0, 1.5 - r]]},
                {"cubic": [[s, 1.5 - r], [r, 1.5 - s], [r, 1.5]]},
            ],
            "closed": True,
        }

    square = {
        "start": [-1.5, -3.5],
        "segments": [{"line": [1.5, -3.5]}, {"line": [1.5, -1.5]}, {"line": [-1.5, -1.5]}],
        "closed": True,
    }
    return [
        group(
            "middle",
            {
                "type": "path",
                "subpaths": [{"start": [-4, 0], "segments": [{"line": [4, 0]}]}],
                "stroke": {"color": "#FFFFFF", "width": 4},
            },
        ),
        group(
            "ring",
            {
                "type": "path",
                "subpaths": [circle(1.2), circle(0.6)],
                "fill": {"color": "#83C167", "rule": "evenodd"},
            },
        ),
        group(
            "dashed",
            {
                "type": "path",
                "subpaths": [square],
                "stroke": {"color": "#FFD43B", "width": 6, "dash": [25, 14]},
            },
        ),
    ]


def thickness(image: Any, background: int) -> int:
    """Rows the middle line covers in the frame's middle column (half-covered rows count half)."""
    column = np.abs(image[:, image.shape[1] // 2].max(axis=1) - background)
    middle = column[image.shape[0] // 2 - 20 : image.shape[0] // 2 + 20]
    return round(float(middle.sum()) / float(255 - background))


@pytest.mark.parametrize("frame", FRAMES)
def test_the_backends_agree_and_widths_follow_the_short_side(
    bench: Any, group: Any, frame: str
) -> None:
    units, pixels = FRAMES[frame]
    canvas = {"units": units, "pixels": pixels, "background": "#000000"}
    drawn = bench.lir(scene(group), canvas=canvas)
    drawn.assert_alike()
    expected = 4 * min(pixels) / 1080
    assert thickness(drawn.svg, 0) == expected
    assert thickness(drawn.manim, 0) == expected
