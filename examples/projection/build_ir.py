"""build_ir.py for the frame "projection": a and b, and the shadow a casts on b.

This is what the agent writes (analysis §4). The orchestrator runs it in
the run folder: it reads header.json, the header the orchestrator locked
from the brief, adds the body and writes the whole picture to ir.json.
Numbers are worked out here, in Python, not copied by hand; each object
says which of the brief's must_show items it shows (covers).

    irpipe run examples/projection/brief.json examples/projection/build_ir.py
"""

import json
import math
from fractions import Fraction
from pathlib import Path

header = json.loads(Path("header.json").read_text(encoding="utf-8"))

a = (Fraction(2), Fraction(3))
b = (Fraction(4), Fraction(0))
k = (a[0] * b[0] + a[1] * b[1]) / (b[0] ** 2 + b[1] ** 2)  # a.b / b.b, exactly
shadow = (k * b[0], k * b[1])
theta = math.degrees(math.atan2(a[1], a[0]))


def point(p: tuple[Fraction, Fraction]) -> list[float]:
    return [float(p[0]), float(p[1])]


vector = {"type": "line", "in": "P", "start": [0, 0], "stroke_width": 6, "arrows": ["end"]}
objects = [
    {"id": "title", "type": "text", "text": "Projection of a onto b", "at": "safe.center_top",
     "anchor": "center_top", "size": "heading", "weight": "bold"},
    {"id": "drop", "type": "line", "in": "P", "start": "a.tip", "end": "proj_ab.tip",
     "style": "construction", "covers": ["drop"]},
    {"id": "b", **vector, "end": point(b), "color": "b", "covers": ["vectors"],
     "label": {"tex": "b", "at": "tip", "dir": "down_right"}},
    {"id": "a", **vector, "end": point(a), "color": "a", "covers": ["vectors"],
     "label": {"tex": "a", "at": "tip", "dir": "up_right"}},
    {"id": "proj_ab", **vector, "end": point(shadow), "color": "proj", "stroke_width": 9,
     "z": 1, "covers": ["shadow"]},
    {"id": "angle", "type": "arc", "in": "P", "center": [0, 0], "radius": 0.6, "start_angle": 0,
     "end_angle": theta, "stroke_width": 3, "covers": ["angle"],
     "label": {"tex": "\\theta", "at": "mid", "dir": 30, "gap": 0.1}},
    {"id": "origin", "type": "circle", "in": "P", "center": [0, 0], "radius": 0.07,
     "fill": "ink", "color": "none", "z": 2},
    {"id": "formula_name", "type": "text", "text": "projection:", "size": "body"},
    {"id": "formula_tex", "type": "math", "size": "body",
     "tex": "\\operatorname{proj}_b a = \\frac{a \\cdot b}{b \\cdot b}\\, b"},
    {"id": "formula", "type": "stack", "arrange": "row",
     "children": ["formula_name", "formula_tex"], "align": "center_baseline",
     "next_to": "b", "dir": "down", "gap": 0.6, "covers": ["formula"]},
]  # fmt: skip
body = {
    "focus": ["proj_ab"],
    "extra_colors": {"ink": "#FFFFFF"},
    "spaces": [{"id": "P", "origin": [-2.2, -1.0], "unit": 1.1}],
    "objects": objects,
}
Path("ir.json").write_text(json.dumps({**header, **body}, indent=2) + "\n", encoding="utf-8")
