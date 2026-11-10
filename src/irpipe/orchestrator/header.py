"""The locked header: what the orchestrator writes from the brief, and the agent may not change.

    header = header_for(brief, style)     # style = frame_style(brief, lesson)

The brief's ``intent`` is the IR's intent; the frame's style gives the rest:
its render profile becomes the frame (aspect, output pixels, units, safe
area and subtitle band, worked out by Canvas), the typography (language,
font pair, every role's size) and the theme; its concept colors become the
header's colors. The style classes are the project's standard set
(``STYLES``). The agent then writes the body, and the check_header stage
makes sure the header it hands back is this one (analysis §1).
"""

from typing import Any, Final

from irpipe.canvas import Box, Canvas
from irpipe.schema.brief import FrameBrief, Style
from irpipe.schema.ir import IRHeader
from irpipe.schema.render_profile import SubtitleMode

STYLES: Final[dict[str, dict[str, Any]]] = {
    "muted": {"opacity": 0.35},
    "construction": {"dash": [14, 10], "stroke_width": 3, "opacity": 0.6},
}
"""The style classes every picture's header offers: faded, and construction lines."""

DIGITS = 6
"""Decimals the header's lengths keep (a millionth of a unit)."""


def header_for(brief: FrameBrief, style: Style) -> IRHeader:
    """The header of the frame ``brief`` describes, drawn with ``style``.

    Raises ValueError when the render profile cannot make a frame (a
    platform shown at another aspect, no safe area left).
    """
    profile = style.render_profile
    canvas = Canvas.from_profile(profile)
    subtitle: dict[str, Any] = {"mode": profile.subtitle.mode, "lines": profile.subtitle.lines}
    if profile.subtitle.mode is not SubtitleMode.NONE:
        assert canvas.subtitle_band is not None
        subtitle["band"] = _box(canvas.subtitle_band)
    theme = profile.theme
    return IRHeader.model_validate(
        {
            "intent": brief.intent,
            "frame": {
                "aspect": profile.aspect,
                "pixels": canvas.pixels,
                "units": (_short(canvas.units[0]), _short(canvas.units[1])),
                "platform": profile.platform,
                "background": theme.background,
                "subtitle": subtitle,
                "safe": _box(canvas.safe),
            },
            "typography": {
                "lang": profile.typography.lang,
                "text_font": profile.typography.font_pair.text,
                "math": profile.typography.font_pair.math,
                "sizes": profile.typography.sizes(),
            },
            "colors": style.concept_colors,
            "styles": STYLES,
            "theme": {"text": theme.text, "line": theme.line, "stroke_width": theme.stroke_width},
        }
    )


def _box(box: Box) -> tuple[float, float, float, float]:
    return (_short(box.x0), _short(box.y0), _short(box.x1), _short(box.y1))


def _short(value: float) -> float:
    return round(value, DIGITS) + 0.0  # + 0.0 turns -0.0 into 0.0
