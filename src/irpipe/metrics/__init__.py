"""Measuring text and formulas as the target backend will draw them (analysis §3).

Layout happens in the front-end, so the front-end must measure with the
engines the backend will draw with; otherwise labels sit right in one
backend and shifted in another. Measurement therefore sits behind one
interface, ``TextMetrics``, with one provider per set of engines.

Module map:
    base.py     TextMetrics, TextBox, MathBox and the METRICS registry
    pango.py    "pango": text through Pango, formulas through LaTeX, as Manim does
    fixed.py    "fixed": every glyph the same width; needs no fonts (tests)
    latex.py    a formula -> glyph outlines and box (latex + dvisvgm); TexError
    svgpath.py  SVG path data -> straight and Bezier segments
    cache.py    CachedMetrics: answers kept in memory, formulas also on disk
    fonts.py    what fontconfig knows: is a family installed, which characters it lacks
"""

from irpipe.metrics import fixed as fixed
from irpipe.metrics import pango as pango
from irpipe.metrics.base import METRICS, MathBox, TextBox, TextMetrics
from irpipe.metrics.cache import CachedMetrics, default_folder
from irpipe.metrics.latex import MissingToolError, TexError

__all__ = [
    "METRICS",
    "CachedMetrics",
    "MathBox",
    "MissingToolError",
    "TexError",
    "TextBox",
    "TextMetrics",
    "default_folder",
]
