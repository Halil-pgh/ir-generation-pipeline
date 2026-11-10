"""LIR -> scene.py: readable Manim code that draws the picture (analysis §3).

    scene = to_scene(lir, ink=InkMetrics().box)
    scene.code       # the text of scene.py; ``manim -s scene.py Frame`` draws it
    scene.objects    # one SceneObject per IR object, in the order they are built

Every LIR group (one IR object) becomes a function named after its id,
``make_<id>()``, with a ``# ir: objects[3] id=a`` comment above it, and
``construct`` keeps what it returns in a variable of the same name. An
object that holds others receives them as arguments, so every function can
also be called on its own (the harness does, to tie a failure to an object).
How each primitive is drawn is in primitives.py.

    # ir: objects[6] id=origin
    def make_origin():
        origin = Circle(radius=0.077).shift([-2.2, -1, 0])
        origin.set_fill("#FFFFFF", opacity=1).set_stroke(width=0)
        return origin
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from irpipe.backends.manim.code import num, pack
from irpipe.backends.manim.names import Names
from irpipe.backends.manim.primitives import InkBox, Primitives, kind
from irpipe.metrics.latex import TEMPLATE, preamble_for
from irpipe.schema import lir

MANIM_VERSION: Final = "0.22.1"
"""The Manim Community release scene.py is written for (pinned in pyproject.toml)."""

MATH_FONT: Final = "latin-modern"
"""The LIR does not name the math font yet; it is the only one the front-end sets."""

USED_NAMES: Final = frozenset(
    {
        "Arc", "BOLD", "CapStyleType", "Circle", "DEGREES", "Ellipse", "ITALIC", "Line",
        "LineJointType", "MathTex", "ORIGIN", "Polygon", "Rectangle", "RegularPolygon",
        "RoundedRectangle", "Scene", "Sector", "TEX", "Text", "VGroup", "VMobject", "config", "np",
    }
)  # fmt: skip
"""Names the functions of scene.py use; an object named like one is renamed (``Circle_``)."""


@dataclass(frozen=True)
class SceneObject:
    """One IR object in scene.py: its function, the variable that keeps it, its parts."""

    gid: str
    source: str | None
    variable: str
    function: str
    children: tuple[str, ...]
    """Variables of the objects inside it, passed to its function in this order."""

    def entry(self) -> dict[str, object]:
        """What the harness needs to build it on its own (its manifest entry)."""
        return {
            "id": self.gid,
            "function": self.function,
            "variable": self.variable,
            "children": list(self.children),
        }


@dataclass(frozen=True)
class Scene:
    code: str
    objects: tuple[SceneObject, ...]
    """Parts before the objects that hold them: the order ``construct`` builds them in."""


def to_scene(drawing: lir.LIRDocument, ink: InkBox) -> Scene:
    """The scene.py that draws ``drawing``; ``ink`` gives a text's ink box in units."""
    return _Writer(drawing, ink).write()


class _Writer:
    def __init__(self, drawing: lir.LIRDocument, ink: InkBox) -> None:
        self.drawing = drawing
        self.primitives = Primitives(ink)
        groups = lir.walk_groups(drawing.items)
        self.names = Names((g.id for g in groups), reserved=USED_NAMES)
        self.objects: list[SceneObject] = []
        self.functions: list[str] = []
        self.transforms = False

    def write(self) -> Scene:
        top = [self.visit(group) for group in self.drawing.items]
        helpers = self.primitives.helpers | ({"_transform"} if self.transforms else set())
        parts = [_header(self.drawing.canvas)]
        if "TEX" in helpers:
            parts.append(_tex_template())
        parts += [HELPERS[name] for name in ("_path", "_transform") if name in helpers]
        parts += self.functions
        parts.append(_construct(self.objects, top))
        return Scene("\n\n\n".join(parts) + "\n", tuple(self.objects))

    def visit(self, group: lir.Group) -> str:
        """Write the functions of ``group`` and of everything in it; return its variable."""
        children = [self.visit(node) for node in group.children if isinstance(node, lir.Group)]
        variable = self.names.variable(group.id)
        function = self.names.function(group.id)
        self.functions.append(self.function(group, variable, function, children))
        self.objects.append(
            SceneObject(group.id, group.source, variable, function, tuple(children))
        )
        return variable

    def function(self, group: lir.Group, variable: str, function: str, params: list[str]) -> str:
        primitives = [node for node in group.children if not isinstance(node, lir.Group)]
        alone = not params and len(primitives) == 1 and group.transform == lir.IDENTITY
        taken = {*params, *USED_NAMES}
        body: list[str] = []
        members: list[str] = []
        subgroups = iter(params)
        for node in group.children:
            if isinstance(node, lir.Group):
                members.append(next(subgroups))
                continue
            name = variable if alone else _free(kind(node), taken)
            lines = self.primitives.lines(node, name)
            if lines:
                body += lines
                members.append(name)
        if alone and members:
            result = variable
        else:
            result = f"VGroup({', '.join(members)})"
            if group.transform != lir.IDENTITY:
                self.transforms = True
                matrix = ", ".join(num(v, 6) for v in group.transform)
                result = f"_transform({result}, ({matrix}))"
        where = f"{group.source} " if group.source else ""
        head = [f"# ir: {where}id={group.id}", f"def {function}({', '.join(params)}):"]
        return "\n".join(head + [f"    {line}" for line in [*body, f"return {result}"]])


def _free(base: str, taken: set[str]) -> str:
    """``base``, or ``base_2``, ``base_3``... whichever is free; it is then taken."""
    name, count = base, 1
    while name in taken:
        count += 1
        name = f"{base}_{count}"
    taken.add(name)
    return name


def _construct(objects: Sequence[SceneObject], top: list[str]) -> str:
    """``Frame``: every object into its variable, parts first; then the picture, in order."""
    lines = ["class Frame(Scene):", "    def construct(self):"]
    lines += [f"        {o.variable} = {o.function}({', '.join(o.children)})" for o in objects]
    if top:
        column = len("        self.add(")
        joint = "\n" + " " * column
        lines.append(f"        self.add({joint.join(pack(top, column))})")
    else:
        lines.append("        pass  # an empty picture")
    return "\n".join(lines)


def _header(canvas: lir.LIRCanvas) -> str:
    (units_w, units_h), (width, height) = canvas.units, canvas.pixels
    return f'''"""A picture drawn by irpipe from lir.json, for Manim Community {MANIM_VERSION}.

    manim -s scene.py Frame      # draws it and saves the picture as a PNG

Each object of the picture is built by its own function, make_<id>(), named
after the object's id in the IR; the comment above it says where the object
is in ir.json. Every number is the front-end's: positions and lengths are
units (the origin at the center, y up, the short side 9 units long).
"""

import numpy as np
from manim import *

config.frame_width = {num(units_w)}
config.frame_height = {num(units_h)}
config.pixel_width = {width}
config.pixel_height = {height}
config.background_color = "{canvas.background}"'''


def _tex_template() -> str:
    body = TEMPLATE.format(font=preamble_for(MATH_FONT), tex="YourTextHere")
    return (
        "# Formulas are set with the template the front-end measured them with.\n"
        f'TEX = TexTemplate()\nTEX.body = r"""{body}"""'
    )


HELPERS: Final = {
    "_path": '''def _path(*subpaths):
    """A shape from subpaths. A subpath is its start point, then a point for
    each straight segment or three (two handles and the end) for each curve,
    and "close" when it is closed."""
    shape = VMobject()
    for start, *segments in subpaths:
        shape.start_new_path(np.array([*start, 0.0]))
        for segment in segments:
            if segment == "close":
                shape.close_path()
            elif len(segment) == 2:
                shape.add_line_to(np.array([*segment, 0.0]))
            else:
                shape.add_cubic_bezier_curve_to(*(np.array([*p, 0.0]) for p in segment))
    return shape''',
    "_transform": '''def _transform(mobject, matrix):
    """Apply a group's matrix (a, b, c, d, e, f): (x, y) -> (a x + c y + e, b x + d y + f).
    Stroke widths scale with the square root of its area factor, as the front-end's do."""
    a, b, c, d, e, f = matrix
    mobject.apply_matrix([[a, c], [b, d]], about_point=ORIGIN)
    mobject.shift([e, f, 0])
    scale = abs(a * d - b * c) ** 0.5
    for part in mobject.family_members_with_points():
        part.set_stroke(width=part.get_stroke_width() * scale, family=False)
    return mobject''',
}
