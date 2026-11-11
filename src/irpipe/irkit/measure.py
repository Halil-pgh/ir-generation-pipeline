"""Measuring a text or a formula from the script, as the measure stage will (analysis §2.5).

    box = pic.measure_text("Projection of a onto b", size="heading", weight="bold")
    box.width, box.height, box.ascent, box.descent      # frame units
    pic.measure_tex(r"\\frac{a}{b}", size="body", space=P)   # in the units of space P

An agent should not guess how wide a text is: the size depends on the font
and on the engine that sets it. These answers come from the same provider
(irpipe/metrics) and font the pipeline's measure stage uses, with the
header's typography, and in IR units, so a box sized from them fits what is
drawn. A formula that cannot be typeset raises TexError here, with LaTeX's
own message. ``size`` is a role of the header's type scale or reference
pixels; left out, a text is ``body`` size, as in the IR.
"""

from dataclasses import dataclass
from typing import Literal

from irpipe.canvas import units
from irpipe.metrics import METRICS, CachedMetrics, TextBox, TextMetrics, default_folder
from irpipe.schema.ir import IRHeader, Size

DEFAULT_PROVIDER = "pango"
"""The measure stage's own default (pipeline.toml, ``[options.measure] metrics``)."""


@dataclass(frozen=True)
class Box:
    """A text's or a formula's box: ``width``, and how far it reaches above and below its
    baseline; all in frame units (or a space's, when asked for)."""

    width: float
    ascent: float
    descent: float

    @property
    def height(self) -> float:
        return self.ascent + self.descent


class Measurer:
    """Texts and formulas measured with the header's typography; the provider is made on first
    use, so a script that measures nothing needs no fonts."""

    def __init__(self, header: IRHeader, provider: str = DEFAULT_PROVIDER) -> None:
        self._header = header
        self._provider = provider
        self._metrics: TextMetrics | None = None

    def text(
        self,
        text: str,
        size: Size = "body",
        weight: Literal["regular", "bold"] = "regular",
        italic: bool = False,
        scale: tuple[float, float] = (1.0, 1.0),
    ) -> Box:
        """The box of ``text`` in the header's text font; ``scale`` is frame units per unit
        of the space to answer in."""
        found = self._get().text(
            text, font=self._header.typography.text_font, size=self.px(size), weight=weight,
            italic=italic,
        )  # fmt: skip
        return _box(found, scale)

    def tex(self, tex: str, size: Size = "body", scale: tuple[float, float] = (1.0, 1.0)) -> Box:
        """The box of the formula ``tex`` (what goes between the dollars); TexError if it
        cannot be typeset."""
        found = self._get().math(tex, math_font=self._header.typography.math, size=self.px(size))
        return _box(found, scale)

    def px(self, size: Size) -> float:
        """A size in reference pixels: a role of the header's type scale, or a number."""
        if isinstance(size, str):
            value: float = getattr(self._header.typography.sizes, size)
            return value
        return float(size)

    def _get(self) -> TextMetrics:
        if self._metrics is None:
            self._metrics = CachedMetrics(METRICS.get(self._provider)(), default_folder())
        return self._metrics


def _box(found: TextBox, scale: tuple[float, float]) -> Box:
    sx, sy = scale
    return Box(units(found.width) / sx, units(found.ascent) / sy, units(found.descent) / sy)
