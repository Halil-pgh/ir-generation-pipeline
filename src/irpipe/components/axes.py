"""Component "axes": two number lines that cross, with ticks, numbers and names.

    {"id": "ax", "type": "axes", "in": "P", "x_range": [-1, 5, 1], "y_range": [-1, 4, 1],
     "x_label": "x", "y_label": "y"}

``x_range`` and ``y_range`` are ``[min, max]`` or ``[min, max, step]`` (step
1 when left out), in the units of the space the axes are drawn in (``in``),
or of the frame. Draw a graph in the same space and it sits on these axes.
The axes cross where the other is 0, or at the nearer end of its range when
0 is outside it. Ticks stand at every multiple of the step, numbers below
and left of them; the tick and number where the axes cross are left out.
With ``arrows`` each axis runs on a little past its maximum into an
arrowhead, and ``x_label`` / ``y_label`` (TeX) sit beyond the heads.

It opens into a group with the axes' id holding its parts: ``ax.x_axis``,
``ax.y_axis``, ``ax.x_tick_0``…, ``ax.x_number_0``…, ``ax.x_label``,
``ax.y_label`` (the same for y). Tick lengths, gaps and the arrows' run-on
are fixed sizes on the frame, so the axes look the same at any scale.
"""

import math
from typing import Any, Literal

from pydantic import Field

from irpipe.components.base import (
    COMPONENTS,
    Component,
    ComponentError,
    Context,
    Expansion,
    group_of,
    make,
)
from irpipe.schema.color import ColorRef
from irpipe.schema.ir.common import Number, PositiveNumber, Size
from irpipe.schema.ir.objects import Line, Math, ObjectBase

TICK = 0.08
"""Half a tick's length, in frame units."""
GAP = 0.12
"""Between a tick's end (or an arrowhead) and its number or name, in frame units."""
RUN_ON = 0.4
"""How far an axis with an arrowhead runs past its maximum, in frame units."""
MAX_TICKS = 100

type Range = tuple[Number, Number] | tuple[Number, Number, PositiveNumber]


@COMPONENTS.register
class Axes(Component):
    type: Literal["axes"] = "axes"
    x_range: Range
    y_range: Range
    ticks: bool = True
    numbers: bool = True
    arrows: bool = True
    x_label: str | None = Field(default=None, min_length=1)
    """The x axis's name, in TeX."""
    y_label: str | None = Field(default=None, min_length=1)
    color: ColorRef | None = None
    """The lines' and the numbers' color; the theme's when left out."""
    stroke_width: float | None = Field(default=None, gt=0)
    number_size: Size = "caption"

    def expand(self, context: Context) -> Expansion:
        x0, x1, dx = _range(self.x_range, "x_range")
        y0, y1, dy = _range(self.y_range, "y_range")
        ux, uy = context.units(self.space)
        cx, cy = min(max(0.0, x0), x1), min(max(0.0, y0), y1)  # where the axes cross
        run_x, run_y = (RUN_ON / ux, RUN_ON / uy) if self.arrows else (0.0, 0.0)
        tick_x, tick_y = TICK / ux, TICK / uy
        xs = [x for x in _multiples(x0, x1, dx, "x_range") if x != cx]
        ys = [y for y in _multiples(y0, y1, dy, "y_range") if y != cy]

        parts: list[ObjectBase] = []
        common = {"in": self.space, "style": self.style, "color": self.color}
        line = {**common, "stroke_width": self.stroke_width}
        number = {**common, "size": self.number_size}
        heads = ["end"] if self.arrows else []

        def add(model: type[ObjectBase], name: str, **fields: Any) -> None:
            oid = f"{self.id}.{name}"
            parts.append(make(model, oid, context.values, tags=self.made_tags(), **fields))

        add(Line, "x_axis", start=[x0, cy], end=[x1 + run_x, cy], arrows=heads, **line)
        add(Line, "y_axis", start=[cx, y0], end=[cx, y1 + run_y], arrows=heads, **line)
        if self.ticks:
            for k, x in enumerate(xs):
                add(Line, f"x_tick_{k}", start=[x, cy - tick_y], end=[x, cy + tick_y], **line)
            for k, y in enumerate(ys):
                add(Line, f"y_tick_{k}", start=[cx - tick_x, y], end=[cx + tick_x, y], **line)
        if self.numbers:
            for k, x in enumerate(xs):
                below = {"at": [x, cy - tick_y], "dir": "down", "gap": GAP / uy}
                add(Math, f"x_number_{k}", tex=_number(x), **below, **number)
            for k, y in enumerate(ys):
                left = {"at": [cx - tick_x, y], "dir": "left", "gap": GAP / ux}
                add(Math, f"y_number_{k}", tex=_number(y), **left, **number)
        name = {**common, "size": "label"}
        if self.x_label:
            beyond = {"at": [x1 + run_x, cy], "dir": "right", "gap": GAP / ux}
            add(Math, "x_label", tex=self.x_label, **beyond, **name)
        if self.y_label:
            beyond = {"at": [cx, y1 + run_y], "dir": "up", "gap": GAP / uy}
            add(Math, "y_label", tex=self.y_label, **beyond, **name)
        return Expansion(group_of(self, parts, context.values), parts)


def _range(given: tuple[float, ...], field: str) -> tuple[float, float, float]:
    low, high, *rest = given
    if not low < high:
        hint = "give the smaller end first: [min, max] or [min, max, step]"
        raise ComponentError(f"{field} runs from {low:g} to {high:g}", field=field, hint=hint)
    return low, high, rest[0] if rest else 1.0


def _multiples(low: float, high: float, step: float, field: str) -> list[float]:
    """Every multiple of ``step`` from ``low`` to ``high``, both ends included."""
    first, last = math.ceil(low / step - 1e-9), math.floor(high / step + 1e-9)
    count = last - first + 1
    if count > MAX_TICKS:
        hint = "give a larger step: [min, max, step]"
        message = f"{field} gives {count} ticks; at most {MAX_TICKS} are drawn"
        raise ComponentError(message, field=field, hint=hint)
    return [round(k * step, 9) + 0.0 for k in range(first, last + 1)]


def _number(value: float) -> str:
    """A tick's number as TeX: ``3``, ``-0.5``, ``2.25``."""
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if text in {"-0", ""} else text
