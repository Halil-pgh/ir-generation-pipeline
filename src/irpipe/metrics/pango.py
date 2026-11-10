"""Measuring as the Manim backend draws: text through Pango, formulas through LaTeX.

Manim sets text with Pango and the system's fontconfig, and formulas with
LaTeX (analysis §3). This provider uses the same engines, through the
``pango`` extra (pangocffi), so a label measured here sits where Manim
draws it. Metrics are not hinted and glyph positions are not rounded, so a
text twice the size is exactly twice as wide.

Text boxes are Pango's logical extents: the font's ascent and descent, the
same for every string, which keeps baselines steady.
"""

import shutil
import subprocess
from collections.abc import Iterable
from functools import cache
from typing import Any, Literal

from irpipe.metrics.base import METRICS, MathBox, TextBox, TextMetrics
from irpipe.metrics.latex import DESIGN_SIZE_PT, MissingToolError, typeset
from irpipe.metrics.svgpath import Subpath


@METRICS.register
class PangoMetrics(TextMetrics):
    name = "pango"

    def __init__(self) -> None:
        try:
            import cairocffi  # type: ignore[import-untyped]
            import pangocairocffi  # type: ignore[import-untyped]
            import pangocffi  # type: ignore[import-untyped]
        except ImportError as exc:
            raise MissingToolError(
                f"the pango measurer needs pangocffi ({exc}); install the pango extra"
            ) from None
        self._pango = pangocffi
        surface = cairocffi.ImageSurface(cairocffi.FORMAT_ARGB32, 1, 1)
        context = pangocairocffi.create_context(cairocffi.Context(surface))
        options = cairocffi.FontOptions()
        options.set_hint_metrics(cairocffi.HINT_METRICS_OFF)
        options.set_hint_style(cairocffi.HINT_STYLE_NONE)
        pangocairocffi.set_font_options(
            context, pangocairocffi.ffi.cast("void *", options._pointer)
        )
        pangocffi.pango.pango_context_set_round_glyph_positions(context.pointer, False)
        self._keep = (surface, options)  # the context points into these; keep them alive
        self._layout: Any = pangocffi.Layout(context)

    def text(
        self,
        text: str,
        *,
        font: str,
        size: float,
        weight: Literal["regular", "bold"],
        italic: bool,
    ) -> TextBox:
        pango = self._pango
        description = pango.FontDescription()
        description.family = font
        description.weight = pango.Weight.BOLD if weight == "bold" else pango.Weight.NORMAL
        description.style = pango.Style.ITALIC if italic else pango.Style.NORMAL
        description.set_absolute_size(pango.units_from_double(size))
        self._layout.font_description = description
        self._layout.text = text
        _, logical = self._layout.get_extents()
        top = pango.units_to_double(logical.y)
        height = pango.units_to_double(logical.height)
        baseline = pango.units_to_double(self._layout.get_baseline())
        return TextBox(
            width=pango.units_to_double(logical.width),
            ascent=baseline - top,
            descent=top + height - baseline,
        )

    def math(self, tex: str, *, math_font: str, size: float) -> MathBox:
        outline = typeset(tex, math_font=math_font)
        scale = size / DESIGN_SIZE_PT  # the formula's 10 pt em becomes ``size`` pixels
        outlines = tuple(
            Subpath(
                (s.start[0] * scale, s.start[1] * scale),
                [(kind, tuple((x * scale, y * scale) for x, y in pts)) for kind, pts in s.segments],
                s.closed,
            )
            for s in outline.subpaths
        )
        return MathBox(
            width=outline.width * scale,
            ascent=outline.ascent * scale,
            descent=outline.descent * scale,
            outlines=outlines,
        )

    def missing_fonts(self, families: Iterable[str]) -> list[str]:
        return [family for family in families if not _installed(family)]


@cache
def _installed(family: str) -> bool:
    """Does fontconfig, which Pango uses, have ``family`` itself rather than a substitute?"""
    if shutil.which("fc-match") is None:
        return True  # no fontconfig to ask (not Linux); assume the font is there
    found = subprocess.run(
        ["fc-match", "-f", "%{family}", family], capture_output=True, text=True, check=False
    ).stdout
    return family.lower() in (name.strip().lower() for name in found.split(","))
