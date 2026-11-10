"""Text measurement: how big a text is when the target backend draws it (analysis §3).

Layout happens in the front-end, so the front-end must measure text with the
fonts the backend will draw it with; otherwise labels sit right in one
backend and shifted in another. Measurement therefore sits behind one
interface, ``TextMetrics``, with one provider per font engine.

Module map:
    base.py   TextMetrics, TextBox and the METRICS registry
    fixed.py  "fixed": every glyph the same width; needs no fonts (tests, step 6)

The Pango provider for Manim arrives with step 10.
"""

from irpipe.metrics import fixed as fixed
from irpipe.metrics.base import METRICS, TextBox, TextMetrics

__all__ = ["METRICS", "TextBox", "TextMetrics"]
