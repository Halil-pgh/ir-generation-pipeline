"""Checks: readability and composition, run on what was actually drawn (analysis §5).

Each check is one file and registers itself in ``CHECKS`` with the issue
codes it reports; ``pipeline.toml`` lists which run (``[options.check]
checks``) and sets each one's options (``[options.check.<name>]``).
Listing ``irpipe.checks`` under ``plugins`` loads them all.

Module map:
    base.py           Check (name, codes, options_model, check(picture)) and CHECKS
    picture.py        Picture: the LIR flattened into the frame, with owners and relations
    stage.py          stage "check": runs the listed checks; provides ``checked``
    frame.py          "offscreen"      W-OFFSCREEN       past the edge of the frame
    safe_area.py      "safe_area"      W-UNSAFE          outside the safe area
    subtitle.py       "subtitle"       E-SUBTITLE        in the subtitle band
    text_overlap.py   "text_overlap"   W-TEXT-OVERLAP    texts on top of texts
    text_crossed.py   "text_crossed"   W-TEXT-CROSSED    a line through a text
    contrast.py       "contrast"       W-LOW-CONTRAST    text against what is behind it
    text_size.py      "text_size"      W-SMALL-TEXT      text too small to read
    colors.py         "similar_colors" W-SIMILAR-COLORS  colors too alike (CIEDE2000)
    fill_overlap.py   "fill_overlap"   W-FILL-OVERLAP    fills that partly overlap by accident
    group_opacity.py  "group_opacity"  W-GROUP-OPACITY   a faded group's children overlap
    glyphs.py         "glyphs"         W-MISSING-GLYPH   a character the font lacks
"""

from irpipe.checks import colors as colors
from irpipe.checks import contrast as contrast
from irpipe.checks import fill_overlap as fill_overlap
from irpipe.checks import frame as frame
from irpipe.checks import glyphs as glyphs
from irpipe.checks import group_opacity as group_opacity
from irpipe.checks import safe_area as safe_area
from irpipe.checks import subtitle as subtitle
from irpipe.checks import text_crossed as text_crossed
from irpipe.checks import text_overlap as text_overlap
from irpipe.checks import text_size as text_size
from irpipe.checks.base import CHECKS, Check
from irpipe.checks.picture import Picture

__all__ = ["CHECKS", "Check", "Picture"]
