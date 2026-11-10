"""Texts, formulas and baselines: SVG and Manim agree.

Formulas are compared pixel for pixel (both backends draw the same TeX
outlines). Texts are compared by where their ink sits: SVG lets cairosvg
set them and Manim lets Pango, so glyphs differ a little in width and
weight (see the bench, conftest.py).
"""

from pathlib import Path
from typing import Any

import numpy as np
import pytest

pytestmark = pytest.mark.manim

ROOT = Path(__file__).parent.parent.parent
EXAMPLES = sorted((ROOT / "examples").glob("*/ir.json"))


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda path: path.parent.name)
def test_every_example(bench: Any, example: Path) -> None:
    drawn = bench.ir(example.read_text(encoding="utf-8"))
    drawn.assert_alike()
    drawn.assert_texts_alike()


def test_a_text_and_a_formula_on_one_baseline(bench: Any, ir_text: Any) -> None:
    word = {"id": "word", "type": "text", "text": "xxx", "size": 64}
    formula = {"id": "f", "type": "math", "tex": "xxx", "size": 64}
    row = {"id": "row", "type": "stack", "children": ["word", "f"], "arrange": "row"}
    drawn = bench.ir(ir_text([word, formula, {**row, "align": "center_baseline", "at": [0, 0]}]))
    drawn.assert_alike()
    drawn.assert_texts_alike()
    columns = {}  # each item's columns in pixels: x of the box, units -> px
    for group in drawn.lir.items[0].children:
        (item,) = group.children
        columns[group.id] = (int(960 + item.box[0] * 120), int(960 + item.box[2] * 120))
    for image in (drawn.svg, drawn.manim):  # an x sits on the baseline in both alphabets
        bottoms = []
        for left, right in columns.values():
            rows = np.nonzero(image[:, left:right].max(axis=2).max(axis=1) > 128)[0]
            bottoms.append(int(rows.max()))
        assert abs(bottoms[0] - bottoms[1]) <= 1, bottoms


def test_a_text_turned_with_its_group(bench: Any, ir_text: Any) -> None:
    label = {"id": "label", "type": "text", "text": "turned", "size": 52, "at": [0, 0]}
    turned = {"id": "turned", "type": "group", "children": ["label"], "rotate": 90}
    drawn = bench.ir(ir_text([label, turned]))
    drawn.assert_alike()
    drawn.assert_texts_alike()
