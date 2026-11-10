"""A formula -> its glyph outlines and box, through latex and dvisvgm.

The front-end typesets every formula itself (analysis §3): a LaTeX error is
found before anything is drawn, and backends without LaTeX (the SVG
reference) can draw the outlines. The Manim backend will typeset with this
same template, so a formula is measured exactly as it will be drawn.

    outline = typeset(r"\\frac{a}{b}", math_font="latin-modern")
    outline.width, outline.ascent, outline.descent   # TeX points
    outline.subpaths                                 # y up, origin on the baseline

Formulas are set in display style at 10 pt; the caller scales to its size.
"""

import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from irpipe.metrics.svgpath import Point, Subpath, parse_path

DESIGN_SIZE_PT = 10.0
"""The font size formulas are set at; outlines scale linearly from it."""

BP_PER_PT = 72 / 72.27
"""dvisvgm writes big points (1/72 in); TeX sizes are points (1/72.27 in)."""

MATH_FONTS: dict[str, str] = {
    "latin-modern": "\\usepackage[T1]{fontenc}\n\\usepackage{lmodern}",
}
"""Math font name (the header's ``typography.math``) -> its preamble lines."""

TEMPLATE = """\\documentclass[preview]{{standalone}}
{font}
\\usepackage{{amsmath}}
\\usepackage{{amssymb}}
\\begin{{document}}
$\\displaystyle {tex}$
\\end{{document}}
"""

_SVG = "{http://www.w3.org/2000/svg}"
_XLINK = "{http://www.w3.org/1999/xlink}"


class TexError(ValueError):
    """LaTeX could not set the formula; the message is LaTeX's own."""


class MissingToolError(RuntimeError):
    """latex or dvisvgm is not installed, or the math font is unknown."""


@dataclass(frozen=True)
class Outline:
    """A typeset formula in points: y up, the origin at the left end of the baseline."""

    width: float
    ascent: float
    descent: float
    subpaths: tuple[Subpath, ...]


def preamble_for(math_font: str) -> str:
    if math_font not in MATH_FONTS:
        known = ", ".join(MATH_FONTS)
        raise MissingToolError(f"math font '{math_font}' is not supported (supported: {known})")
    return MATH_FONTS[math_font]


def typeset(tex: str, *, math_font: str, timeout: float = 30) -> Outline:
    """Typeset ``tex`` and return its outline. Raises TexError or MissingToolError."""
    font = preamble_for(math_font)
    for tool in ("latex", "dvisvgm"):
        if shutil.which(tool) is None:
            raise MissingToolError(f"{tool} is not installed; formulas cannot be typeset")
    with tempfile.TemporaryDirectory(prefix="irpipe-tex-") as folder:
        work = Path(folder)
        (work / "f.tex").write_text(TEMPLATE.format(font=font, tex=tex), encoding="utf-8")
        latex = subprocess.run(
            ["latex", "-interaction=nonstopmode", "-halt-on-error", "f.tex"],
            cwd=work,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if latex.returncode != 0:
            raise TexError(_latex_error(work / "f.log"))
        svg = subprocess.run(
            ["dvisvgm", "--no-fonts", "--exact-bbox", "-o", "f.svg", "f.dvi"],
            cwd=work,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if svg.returncode != 0 or not (work / "f.svg").exists():
            raise MissingToolError(f"dvisvgm failed: {svg.stderr.decode(errors='replace').strip()}")
        return _read_svg((work / "f.svg").read_text(encoding="utf-8"))


def _latex_error(log: Path) -> str:
    """LaTeX's first error, and where in the formula it stopped (never the template)."""
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines() if log.exists() else []
    for k, line in enumerate(lines):
        if not line.startswith("! "):
            continue
        message = line[2:].rstrip(".")
        for later in lines[k + 1 : k + 6]:
            match = re.match(r"l\.\d+ (.*)", later)
            if match:
                written = match.group(1).replace("$\\displaystyle ", "", 1).strip().rstrip("$")
                if written:
                    return f"{message}, after: {written[-40:]}"
        return message.strip()
    return "LaTeX stopped without saying why"


def _read_svg(text: str) -> Outline:
    """dvisvgm's SVG (big points, y down) -> an outline in points, y up."""
    root = ET.fromstring(text)
    left, top, width, height = (float(v) for v in root.attrib["viewBox"].split())
    scale = 1 / BP_PER_PT
    glyphs = {p.attrib["id"]: p.attrib.get("d", "") for p in root.iter(f"{_SVG}path")}
    subpaths: list[Subpath] = []

    def place(point: Point, dx: float, dy: float) -> Point:
        return ((point[0] + dx - left) * scale, -(point[1] + dy) * scale)

    for use in root.iter(f"{_SVG}use"):
        ref = use.attrib.get(f"{_XLINK}href") or use.attrib.get("href", "")
        dx, dy = float(use.attrib.get("x", 0)), float(use.attrib.get("y", 0))
        for subpath in parse_path(glyphs.get(ref.lstrip("#"), "")):
            subpaths.append(
                Subpath(
                    place(subpath.start, dx, dy),
                    [
                        (kind, tuple(place(p, dx, dy) for p in points))
                        for kind, points in subpath.segments
                    ],
                    subpath.closed,
                )
            )
    for rect in root.iter(f"{_SVG}rect"):  # fraction bars and other rules
        x, y = float(rect.attrib["x"]), float(rect.attrib["y"])
        w, h = float(rect.attrib["width"]), float(rect.attrib["height"])
        corners = [place(c, 0, 0) for c in ((x, y), (x + w, y), (x + w, y + h), (x, y + h))]
        subpaths.append(Subpath(corners[0], [("line", (c,)) for c in corners[1:]], closed=True))
    return Outline(
        width=width * scale,
        ascent=-top * scale,
        descent=(height + top) * scale,
        subpaths=tuple(subpaths),
    )
