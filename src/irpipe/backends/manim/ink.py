"""Where a text's glyphs reach: its ink box, as Pango sets it.

Manim's ``Text`` keeps no baseline: its outline is centered where Manim
puts it, so it can only be placed by its ink, the box its glyphs fill. The
LIR carries a text's logical box (the advance width, the font's ascent and
descent) and its baseline. This module adds where the ink sits inside that
box, measured with the same Pango settings the front-end measured with
(metrics/pango.py): no hinting, no rounding. Manim draws ``Text`` with
Pango too, so its outline fills exactly this box (within a thousandth).

    ink = InkMetrics()
    ink.box(text_item)    # (left, bottom, right, top) in units, or None when nothing shows
"""

from irpipe.canvas import units
from irpipe.metrics.pango import PangoMetrics
from irpipe.schema.lir import Box, TextItem


class InkMetrics(PangoMetrics):
    """The pango measurer, asked for a text's ink instead of its logical box.

    Not registered as a measurer: the front-end measures with "pango"; only
    the Manim backend asks where the ink lies. Raises MissingToolError when
    pangocffi is not installed.
    """

    def box(self, item: TextItem) -> Box | None:
        """The ink box of ``item`` in units, in the frame; None for a text that draws nothing."""
        self.text(item.text, font=item.font, size=item.size, weight=item.weight, italic=item.italic)
        ink, logical = self._layout.get_extents()
        to_px = self._pango.units_to_double
        if ink.width <= 0 or ink.height <= 0:  # only spaces
            return None
        baseline = to_px(self._layout.get_baseline())
        left = to_px(ink.x) - to_px(logical.x)
        top = baseline - to_px(ink.y)
        x, y = item.box[0], item.baseline  # the left end of the baseline, in the frame
        return (
            x + units(left),
            y + units(top - to_px(ink.height)),
            x + units(left + to_px(ink.width)),
            y + units(top),
        )
