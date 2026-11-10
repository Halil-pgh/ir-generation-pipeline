"""The paint cascade: what an object is drawn with once nothing is left to inherit.

A paint field the object leaves out comes from its style classes (a later
class wins), and what no class sets comes from the theme (analysis §2.8):

    theme defaults -> style classes, in the order listed -> the object

The theme's line and text color is whichever of white or black contrasts
more with the background. Color names become hex: a header color, an
extra color, or a mix of two (the average of their channels). ``"none"``
becomes ``None``: nothing is painted.
"""

from dataclasses import dataclass
from typing import Any, Literal, cast

from irpipe.schema.color import NO_PAINT, Color, ColorRef, Mix, to_rgb
from irpipe.schema.ir import IRDocument, Style
from irpipe.schema.ir.objects import ObjectBase

DEFAULT_STROKE_WIDTH = 4.0
"""Reference px of a line no style or object gives a width."""

PAINT_FIELDS = tuple(Style.model_fields)


@dataclass(frozen=True)
class Paint:
    """Every paint and text field after the cascade; colors are hex, or None for no paint."""

    color: str | None
    fill: str | None
    fill_opacity: float
    opacity: float
    stroke_width: float
    dash: tuple[float, ...] | None
    size: float
    weight: Literal["regular", "bold"]
    italic: bool


def to_hex(color: Color) -> str:
    r, g, b = to_rgb(color)
    return f"#{r:02X}{g:02X}{b:02X}"


def foreground_for(background: Color) -> str:
    """White or black, whichever contrasts more with ``background`` (WCAG contrast)."""
    lum = _luminance(to_rgb(background))
    return "#FFFFFF" if 1.05 / (lum + 0.05) >= (lum + 0.05) / 0.05 else "#000000"


def _luminance(rgb: tuple[int, int, int]) -> float:
    def linear(channel: int) -> float:
        c = channel / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


class PaintResolver:
    """Resolves paint for the objects of one checked IR document."""

    def __init__(self, document: IRDocument) -> None:
        self._document = document
        self._defaults: dict[str, Any] = {
            "color": foreground_for(document.frame.background),
            "fill": NO_PAINT,
            "fill_opacity": 1.0,
            "opacity": 1.0,
            "stroke_width": DEFAULT_STROKE_WIDTH,
            "dash": None,
            "size": "body",
            "weight": "regular",
            "italic": False,
        }

    def paint(self, obj: ObjectBase) -> Paint:
        values = dict(self._defaults)
        for name in obj.style_names:
            values.update(_set_fields(self._document.styles[name]))
        values.update(_set_fields(obj))
        return Paint(
            color=self.color(values["color"]),
            fill=self.color(values["fill"]),
            fill_opacity=float(values["fill_opacity"]),
            opacity=float(values["opacity"]),
            stroke_width=float(values["stroke_width"]),
            dash=values["dash"],
            size=self.size(values["size"]),
            weight=cast(Literal["regular", "bold"], values["weight"]),
            italic=bool(values["italic"]),
        )

    def color(self, ref: ColorRef) -> str | None:
        """Hex for a literal or a name; None for ``"none"``."""
        if isinstance(ref, tuple) or ref.startswith("#"):
            return to_hex(ref)
        if ref == NO_PAINT:
            return None
        if ref in self._document.colors:
            return to_hex(self._document.colors[ref])
        extra = self._document.extra_colors[ref]
        if isinstance(extra, Mix):
            (r1, g1, b1), (r2, g2, b2) = (to_rgb(self._literal(part)) for part in extra.mix)
            return to_hex((round((r1 + r2) / 2), round((g1 + g2) / 2), round((b1 + b2) / 2)))
        return to_hex(extra)

    def size(self, value: float | str) -> float:
        """Reference px for a size or a text role."""
        if isinstance(value, str):
            return float(getattr(self._document.typography.sizes, value))
        return float(value)

    def _literal(self, ref: ColorRef) -> Color:
        """A mix's part: a literal color or a header color name (validate made sure)."""
        if isinstance(ref, str) and not ref.startswith("#"):
            return self._document.colors[ref]
        return ref


def _set_fields(source: object) -> dict[str, Any]:
    """The paint fields ``source`` sets (leaves out the ones that are None)."""
    fields = {name: getattr(source, name, None) for name in PAINT_FIELDS}
    return {name: value for name, value in fields.items() if value is not None}
