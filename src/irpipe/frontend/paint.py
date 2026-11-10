"""The paint cascade: what an object is drawn with once nothing is left to inherit.

A paint field the object leaves out comes from its style classes (a later
class wins), and what no class sets comes from the header's theme
(analysis §2.8):

    theme defaults -> style classes, in the order listed -> the object

The theme gives texts and formulas its text color and everything else its
line color;
a theme color left out is white or black, whichever contrasts more with the
background. Color names become hex: a header color, an extra color, or a mix
of two (the average of their channels). ``"none"`` means nothing is painted.

``PaintResolver.normalized`` writes the result back into the object's own
fields (the normalize stage); ``painted`` reads it from there (resolve).
"""

from dataclasses import dataclass
from typing import Any, Literal, cast

from irpipe.schema.color import NO_PAINT, Color, ColorRef, Mix, to_rgb
from irpipe.schema.ir import IRDocument, Math, Style, Text
from irpipe.schema.ir.objects import ObjectBase

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
        theme = document.theme
        contrast = foreground_for(document.frame.background)
        self._text_color: ColorRef = theme.text if theme.text is not None else contrast
        self._line_color: ColorRef = theme.line if theme.line is not None else contrast
        self._defaults: dict[str, Any] = {
            "fill": NO_PAINT,
            "fill_opacity": 1.0,
            "opacity": 1.0,
            "stroke_width": theme.stroke_width,
            "dash": None,
            "size": "body",
            "weight": "regular",
            "italic": False,
        }

    def paint(self, obj: ObjectBase) -> Paint:
        """The cascade for ``obj``: theme, then its style classes, then its own fields."""
        values = dict(self._defaults)
        values["color"] = self._text_color if isinstance(obj, Text | Math) else self._line_color
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

    def normalized[T: ObjectBase](self, obj: T) -> T:
        """``obj`` with every paint field it has written out and its style classes gone."""
        paint = self.paint(obj)
        fields = type(obj).model_fields
        update: dict[str, Any] = {"style": None, "opacity": paint.opacity}
        if "color" in fields:
            update["color"] = paint.color or NO_PAINT
        if "fill" in fields:
            update |= {"fill": paint.fill or NO_PAINT, "fill_opacity": paint.fill_opacity}
        if "stroke_width" in fields:
            update |= {"stroke_width": paint.stroke_width, "dash": paint.dash}
        if "size" in fields:
            update |= {"size": paint.size, "weight": paint.weight, "italic": paint.italic}
        return obj.model_copy(update={k: v for k, v in update.items() if k in fields})

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


def painted(obj: ObjectBase) -> Paint:
    """The paint of an object normalize has written out; no cascade is needed any more."""

    def field(name: str, default: Any) -> Any:
        value = getattr(obj, name, None)
        return default if value is None else value

    def hex_or_none(name: str) -> str | None:
        value = field(name, NO_PAINT)
        return None if value == NO_PAINT else str(value)

    return Paint(
        color=hex_or_none("color"),
        fill=hex_or_none("fill"),
        fill_opacity=float(field("fill_opacity", 1.0)),
        opacity=float(field("opacity", 1.0)),
        stroke_width=float(field("stroke_width", 0.0)),
        dash=field("dash", None),
        size=float(field("size", 0.0)),
        weight=field("weight", "regular"),
        italic=bool(field("italic", False)),
    )


def _set_fields(source: object) -> dict[str, Any]:
    """The paint fields ``source`` sets (leaves out the ones that are None)."""
    fields = {name: getattr(source, name, None) for name in PAINT_FIELDS}
    return {name: value for name, value in fields.items() if value is not None}
