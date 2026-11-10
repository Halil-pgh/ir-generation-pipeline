"""LIR -> SVG text, in plain Python.

LIR positions are units (origin at the center, y up); the SVG is written in
output pixels (origin top left, y down), so a reader of frame.svg sees plain
pixel numbers and text is never mirrored. Every IR object is a
``<g id="...">`` carrying its id and its JSON path in the IR.

    svg_text = to_svg(lir)
"""

import xml.etree.ElementTree as ET
from collections.abc import Iterable

from irpipe.canvas import REFERENCE_SHORT_SIDE_PX
from irpipe.schema.lir import (
    IDENTITY,
    CubicTo,
    FillPaint,
    Group,
    ImageItem,
    LineTo,
    LIRCanvas,
    LIRDocument,
    MathItem,
    PathItem,
    Point,
    QuadTo,
    StrokePaint,
    Subpath,
    TextItem,
)

SVG_NAMESPACE = "http://www.w3.org/2000/svg"
TEXT_ANCHOR = {"left": "start", "center": "middle", "right": "end"}


def num(value: float) -> str:
    """A short, stable number: at most three decimals, no trailing zeros."""
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return "0" if text in {"-0", ""} else text


class Frame:
    """Maps one LIR canvas from units to output pixels."""

    def __init__(self, canvas: LIRCanvas) -> None:
        (width, height), (units_w, units_h) = canvas.pixels, canvas.units
        self.width, self.height = width, height
        self.kx, self.ky = width / units_w, height / units_h  # pixels per unit
        self.cx, self.cy = width / 2, height / 2
        self.reference = min(width, height) / REFERENCE_SHORT_SIDE_PX

    def point(self, point: Point) -> str:
        x, y = point
        return f"{num(self.cx + x * self.kx)} {num(self.cy - y * self.ky)}"

    def x(self, x: float) -> float:
        return self.cx + x * self.kx

    def y(self, y: float) -> float:
        return self.cy - y * self.ky

    def length(self, reference_px: float) -> float:
        """A width, dash or type size in reference pixels, in output pixels."""
        return reference_px * self.reference

    def matrix(self, m: tuple[float, float, float, float, float, float]) -> str:
        """A LIR matrix (units, y up) as an SVG ``matrix(...)`` in pixels (y down)."""
        a, b, c, d, e, f = m
        kx, ky, cx, cy = self.kx, self.ky, self.cx, self.cy
        values = (
            a,
            -b * ky / kx,
            -c * kx / ky,
            d,
            cx * (1 - a) + c * (kx / ky) * cy + kx * e,
            cy * (1 - d) + b * (ky / kx) * cx - ky * f,
        )
        return f"matrix({' '.join(num(v) for v in values)})"


def to_svg(lir: LIRDocument) -> str:
    frame = Frame(lir.canvas)
    root = ET.Element(
        "svg",
        {
            "xmlns": SVG_NAMESPACE,
            "width": str(frame.width),
            "height": str(frame.height),
            "viewBox": f"0 0 {frame.width} {frame.height}",
        },
    )
    ET.SubElement(
        root,
        "rect",
        {"width": str(frame.width), "height": str(frame.height), "fill": lir.canvas.background},
    )
    for group in lir.items:
        root.append(_group(group, frame))
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode") + "\n"


def _group(group: Group, frame: Frame) -> ET.Element:
    element = ET.Element("g", {"id": group.id})
    if group.source is not None:
        element.set("data-source", group.source)
    if group.transform != IDENTITY:
        element.set("transform", frame.matrix(group.transform))
    for node in group.children:
        if isinstance(node, Group):
            element.append(_group(node, frame))
        elif isinstance(node, PathItem):
            element.append(_path(node, frame))
        elif isinstance(node, TextItem):
            element.append(_text(node, frame))
        elif isinstance(node, MathItem):
            element.append(_math(node, frame))
        elif isinstance(node, ImageItem):
            element.append(_image(node, frame))
    return element


def path_data(subpaths: Iterable[Subpath], frame: Frame) -> str:
    """SVG path commands: M, L, Q, C and Z, in pixels."""
    parts: list[str] = []
    for subpath in subpaths:
        parts.append(f"M {frame.point(subpath.start)}")
        for segment in subpath.segments:
            if isinstance(segment, LineTo):
                parts.append(f"L {frame.point(segment.line)}")
            elif isinstance(segment, QuadTo):
                parts.append("Q " + " ".join(frame.point(p) for p in segment.quad))
            elif isinstance(segment, CubicTo):
                parts.append("C " + " ".join(frame.point(p) for p in segment.cubic))
        if subpath.closed:
            parts.append("Z")
    return " ".join(parts)


def _path(item: PathItem, frame: Frame) -> ET.Element:
    element = ET.Element("path", {"d": path_data(item.subpaths, frame)})
    _fill(element, item.fill)
    _stroke(element, item.stroke, frame)
    return element


def _fill(element: ET.Element, fill: FillPaint | None) -> None:
    if fill is None:
        element.set("fill", "none")
        return
    element.set("fill", fill.color)
    if fill.opacity != 1:
        element.set("fill-opacity", num(fill.opacity))
    if fill.rule == "evenodd":
        element.set("fill-rule", "evenodd")


def _stroke(element: ET.Element, stroke: StrokePaint | None, frame: Frame) -> None:
    if stroke is None:
        return
    element.set("stroke", stroke.color)
    element.set("stroke-width", num(frame.length(stroke.width)))
    if stroke.opacity != 1:
        element.set("stroke-opacity", num(stroke.opacity))
    if stroke.dash:
        element.set("stroke-dasharray", " ".join(num(frame.length(d)) for d in stroke.dash))
    if stroke.cap != "butt":
        element.set("stroke-linecap", stroke.cap)
    if stroke.join != "miter":
        element.set("stroke-linejoin", stroke.join)


def _text(item: TextItem, frame: Frame) -> ET.Element:
    """Placed by its anchor horizontally and by the measured baseline vertically."""
    horizontal = "center" if item.anchor == "center" else item.anchor.split("_")[0]
    element = ET.Element(
        "text",
        {
            "x": num(frame.x(item.at[0])),
            "y": num(frame.y(item.baseline)),
            "font-family": f"{item.font}, sans-serif",
            "font-size": num(frame.length(item.size)),
            "fill": item.color,
            "text-anchor": TEXT_ANCHOR[horizontal],
        },
    )
    if item.weight == "bold":
        element.set("font-weight", "bold")
    if item.italic:
        element.set("font-style", "italic")
    if item.opacity != 1:
        element.set("fill-opacity", num(item.opacity))
    element.text = item.text
    return element


def _math(item: MathItem, frame: Frame) -> ET.Element:
    """A formula drawn from its glyph outlines (the render stage made sure there are some)."""
    element = ET.Element("path", {"d": path_data(item.glyphs, frame), "fill": item.color})
    if item.opacity != 1:
        element.set("fill-opacity", num(item.opacity))
    element.set("data-tex", item.tex)
    return element


def _image(item: ImageItem, frame: Frame) -> ET.Element:
    x0, y0, x1, y1 = item.box
    element = ET.Element(
        "image",
        {
            "href": item.src,
            "x": num(frame.x(x0)),
            "y": num(frame.y(y1)),
            "width": num((x1 - x0) * frame.kx),
            "height": num((y1 - y0) * frame.ky),
            "preserveAspectRatio": "none",
        },
    )
    if item.opacity != 1:
        element.set("opacity", num(item.opacity))
    return element
