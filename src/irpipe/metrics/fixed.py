"""A text measurer that needs no fonts: every glyph has the same width.

Its numbers are only a rough stand-in for real glyphs, but they are exactly
the same on every machine, so tests never depend on installed fonts. Until
the Pango provider arrives (step 10) the pipeline uses it too.
"""

from typing import ClassVar, Literal

from irpipe.metrics.base import METRICS, TextBox, TextMetrics


@METRICS.register
class FixedMetrics(TextMetrics):
    name = "fixed"

    ADVANCE: ClassVar[float] = 0.55  # glyph width, as a share of the size
    BOLD: ClassVar[float] = 1.06  # bold glyphs are a little wider
    ASCENT: ClassVar[float] = 0.75
    DESCENT: ClassVar[float] = 0.25

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
