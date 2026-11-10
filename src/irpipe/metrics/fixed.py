"""A measurer that needs no fonts and no LaTeX: every glyph has the same width.

Its numbers are only a rough stand-in for real glyphs, but they are exactly
the same on every machine, so tests never depend on installed fonts. A
formula gets a box but no outlines, so a backend without LaTeX cannot draw
it; use "pango" for real pictures.
"""

from typing import ClassVar, Literal

from irpipe.metrics.base import METRICS, MathBox, TextBox, TextMetrics


@METRICS.register
class FixedMetrics(TextMetrics):
    name = "fixed"

    ADVANCE: ClassVar[float] = 0.55  # glyph width, as a share of the size
    BOLD: ClassVar[float] = 1.06  # bold glyphs are a little wider
    ASCENT: ClassVar[float] = 0.75
    DESCENT: ClassVar[float] = 0.25
    # Per character of TeX source, which is longer than the glyphs it makes.
    TEX_ADVANCE: ClassVar[float] = 0.4

    def text(
        self,
        text: str,
        *,
        font: str,
        size: float,
        weight: Literal["regular", "bold"],
        italic: bool,
    ) -> TextBox:
        widen = self.BOLD if weight == "bold" else 1.0
        return TextBox(
            width=len(text) * size * self.ADVANCE * widen,
            ascent=size * self.ASCENT,
            descent=size * self.DESCENT,
        )

    def math(self, tex: str, *, math_font: str, size: float) -> MathBox:
        return MathBox(
            width=len(tex) * size * self.TEX_ADVANCE,
            ascent=size * self.ASCENT,
            descent=size * self.DESCENT,
        )
