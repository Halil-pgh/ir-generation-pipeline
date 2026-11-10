"""One LIR primitive -> the lines of scene.py that build it with Manim's classes.

    primitives = Primitives(ink=InkMetrics().box)
    primitives.lines(path_item, "circle")   # ['circle = Circle(radius=0.08).shift([...])', ...]
    primitives.helpers                      # {"_path", "TEX"}: what those lines rely on

A path made from a known shape is drawn by Manim's class for it, with the
hint's numbers (``Circle(radius=...)``), as long as the hint still describes
the whole path; any other path is built point by point with ``_path``.
Texts are ``Text`` and formulas ``MathTex``, at the size the front-end
measured, moved onto the box their glyphs fill. Every number is the
front-end's; how Manim turns them into pixels is in the constants below.
"""

import math
from collections.abc import Callable, Sequence
from typing import Final

from irpipe.backends.manim.code import (
    BODY,
    Call,
    degrees,
    num,
    pack,
    tex_literal,
    text_literal,
    xy,
    xyz,
)
from irpipe.canvas import REFERENCE_PX_PER_UNIT, units
from irpipe.metrics.latex import BP_PER_PT, DESIGN_SIZE_PT
from irpipe.schema import lir

LINE_WIDTH_UNITS: Final = 0.01
"""Units Manim's cairo camera draws a stroke width of 1 as (``cairo_line_width_multiple``)."""

TEXT_EM_UNITS_PER_FONT_SIZE: Final = 1 / 72
"""``Text`` at ``font_size`` F has an em of F / 72 units: Pango sets it at F / 4.8 pt in an
SVG of 96 px per inch, which Manim scales by 0.05."""

MATH_UNITS_PER_BP_PER_FONT_SIZE: Final = 1 / 960
"""``MathTex`` at ``font_size`` F draws one TeX big point as F / 960 units."""

CLOSED_SHAPES: Final = frozenset(
    {"circle", "ellipse", "rect", "regular_polygon", "polygon", "sector"}
)
SAME_POINT: Final = 1e-4
"""Units within which two end points are the same (about a hundredth of a pixel)."""

CAPS = {"round": "ROUND", "square": "SQUARE"}  # butt is Manim's default
JOINS = {"round": "ROUND", "bevel": "BEVEL"}  # and so is miter

type InkBox = Callable[[lir.TextItem], lir.Box | None]


class Primitives:
    """Writes primitives; ``helpers`` collects the module-level names they rely on."""

    def __init__(self, ink: InkBox) -> None:
        self.ink = ink
        self.helpers: set[str] = set()

    def lines(self, node: lir.Node, name: str) -> list[str]:
        """The lines that build ``node`` into the variable ``name``; none when nothing shows."""
        if isinstance(node, lir.PathItem):
            return self.path(node, name)
        if isinstance(node, lir.TextItem):
            return self.text(node, name)
        if isinstance(node, lir.MathItem):
            return self.math(node, name)
        raise TypeError(f"scene.py cannot draw {type(node).__name__}; lower the LIR first")

    def path(self, item: lir.PathItem, name: str) -> list[str]:
        call = shape_call(item.hint) if item.hint and fits(item.hint, item.subpaths) else None
        if call is None:
            self.helpers.add("_path")
            call = Call("_path", [_subpath(s) for s in item.subpaths])
        lines = [*call.assign(name), f"{name}{_fill(item.fill)}{_stroke(item.stroke)}"]
        if item.stroke is not None and item.stroke.cap in CAPS:
            lines.append(f"{name}.set_cap_style(CapStyleType.{CAPS[item.stroke.cap]})")
        if item.stroke is not None and item.stroke.join in JOINS:
            lines.append(f"{name}.joint_type = LineJointType.{JOINS[item.stroke.join]}")
        return lines

    def text(self, item: lir.TextItem, name: str) -> list[str]:
        box = self.ink(item)
        if box is None:
            return []  # only spaces
        size = num(units(item.size) / TEXT_EM_UNITS_PER_FONT_SIZE, 3)
        args = [text_literal(item.text), f"font={text_literal(item.font)}", f"font_size={size}"]
        args += ["weight=BOLD"] * (item.weight == "bold") + ["slant=ITALIC"] * item.italic
        return [
            *Call("Text", args).assign(name),
            f'{name}.set_fill("{item.color}", opacity={num(item.opacity)})',
            f"{name}.move_to({_center(box)})",
        ]

    def math(self, item: lir.MathItem, name: str) -> list[str]:
        self.helpers.add("TEX")
        em = DESIGN_SIZE_PT * BP_PER_PT  # the formula's 10 pt em, in big points
        size = num(units(item.size) / em / MATH_UNITS_PER_BP_PER_FONT_SIZE, 3)
        args = [tex_literal(item.tex), "tex_template=TEX", "tex_environment=None"]
        return [
            *Call("MathTex", [*args, f"font_size={size}"]).assign(name),
            f'{name}.set_fill("{item.color}", opacity={num(item.opacity)})',
            f"{name}.move_to({_center(item.box)})",
        ]


def kind(node: lir.Node) -> str:
    """A name for a primitive inside its object's function: line, circle, text..."""
    if isinstance(node, lir.PathItem):
        if node.hint is None:
            return "shape"
        return "polygon" if node.hint.shape == "regular_polygon" else node.hint.shape
    return "formula" if isinstance(node, lir.MathItem) else node.type


# -- shapes -------------------------------------------------------------------


def fits(hint: lir.ShapeHint, subpaths: Sequence[lir.Subpath]) -> bool:
    """Whether ``hint`` still describes ``subpaths``: the whole shape, not dashes cut from it.

    Manim draws the hint's shape instead of the points, so the two must be
    the same geometry. A closed shape is one closed subpath; an open one is
    one open subpath that starts and ends where the shape does.
    """
    if len(subpaths) != 1:
        return False
    (subpath,) = subpaths
    if hint.shape in CLOSED_SHAPES or subpath.closed:
        return hint.shape in CLOSED_SHAPES and subpath.closed
    drawn = [subpath.start, *(_end(segment) for segment in subpath.segments)]
    match hint:
        case lir.LineHint(start=p, end=q):
            expected, drawn = [p, q], [drawn[0], drawn[-1]]
        case lir.PolylineHint(points=points):
            expected = list(points)
        case lir.ArcHint(center=c, radius=r, start_angle=a, end_angle=b):
            expected, drawn = [_on_circle(c, r, a), _on_circle(c, r, b)], [drawn[0], drawn[-1]]
        case _:
            return False
    return len(expected) == len(drawn) and all(
        math.dist(p, q) <= SAME_POINT for p, q in zip(expected, drawn, strict=True)
    )


def shape_call(hint: lir.ShapeHint) -> Call:
    """The Manim class that draws ``hint``'s shape, with the hint's own numbers."""
    match hint:
        case lir.CircleHint(center=c, radius=r):
            return Call("Circle", [f"radius={num(r)}"], _shift(c))
        case lir.EllipseHint(center=c, rx=rx, ry=ry):
            return Call("Ellipse", [f"width={num(2 * rx)}", f"height={num(2 * ry)}"], _shift(c))
        case lir.RectHint(center=c, width=w, height=h, corner_radius=0):
            return Call("Rectangle", [f"width={num(w)}", f"height={num(h)}"], _shift(c))
        case lir.RectHint(center=c, width=w, height=h, corner_radius=r):
            args = [f"corner_radius={num(r)}", f"width={num(w)}", f"height={num(h)}"]
            return Call("RoundedRectangle", args, _shift(c))
        case lir.RegularPolygonHint(center=c, radius=r, sides=n, rotation=turn):
            start = turn - 90 + 180 / n  # rotation 0 stands on a flat bottom edge
            args = [f"n={n}", f"radius={num(r)}", f"start_angle={degrees(start)}"]
            return Call("RegularPolygon", args, _shift(c))
        case lir.PolygonHint(points=points):
            return Call("Polygon", [xyz(p) for p in points])
        case lir.SectorHint(center=c, radius=r, start_angle=a, end_angle=b):
            args = [f"radius={num(r)}", f"start_angle={degrees(a)}", f"angle={degrees(b - a)}"]
            return Call("Sector", args, _shift(c))
        case lir.ArcHint(center=c, radius=r, start_angle=a, end_angle=b):
            args = [f"radius={num(r)}", f"start_angle={degrees(a)}", f"angle={degrees(b - a)}"]
            return Call("Arc", args, _shift(c))
        case lir.LineHint(start=p, end=q):
            return Call("Line", [xyz(p), xyz(q)])
        case lir.PolylineHint(points=points):
            corners = f"[{', '.join(xyz(p) for p in points)}]"
            return Call("VMobject().set_points_as_corners", [corners])
    raise TypeError(f"unknown hint {hint!r}")


def _subpath(subpath: lir.Subpath) -> str:
    """One argument of ``_path``: the start, a point per line, three per curve, "close"."""
    tokens = [xy(subpath.start)]
    for segment in subpath.segments:
        match segment:
            case lir.LineTo(line=p):
                tokens.append(xy(p))
            case lir.CubicTo(cubic=(c1, c2, p)):
                tokens.append(f"({xy(c1)}, {xy(c2)}, {xy(p)})")
            case lir.QuadTo():
                raise TypeError("quadratic segments reach scene.py only after lowering")
    if subpath.closed:
        tokens.append('"close"')
    return "[" + "\n ".join(pack(tokens, column=BODY + 5)) + "]"


def _fill(fill: lir.FillPaint | None) -> str:
    if fill is None:
        return ".set_fill(opacity=0)"
    return f'.set_fill("{fill.color}", opacity={num(fill.opacity)})'


def _stroke(stroke: lir.StrokePaint | None) -> str:
    if stroke is None:
        return ".set_stroke(width=0)"
    width = num(stroke.width / (REFERENCE_PX_PER_UNIT * LINE_WIDTH_UNITS), 3)
    opacity = "" if stroke.opacity == 1 else f", opacity={num(stroke.opacity)}"
    return f'.set_stroke("{stroke.color}", width={width}{opacity})'


def _shift(center: lir.Point) -> str:
    return "" if center == (0, 0) else f".shift({xyz(center)})"


def _center(box: lir.Box) -> str:
    return xyz(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2))


def _on_circle(center: lir.Point, radius: float, angle: float) -> lir.Point:
    turn = math.radians(angle)
    return (center[0] + radius * math.cos(turn), center[1] + radius * math.sin(turn))


def _end(segment: lir.Segment) -> lir.Point:
    match segment:
        case lir.LineTo(line=p) | lir.QuadTo(quad=(_, p)) | lir.CubicTo(cubic=(_, _, p)):
            return p
    raise TypeError(segment)
