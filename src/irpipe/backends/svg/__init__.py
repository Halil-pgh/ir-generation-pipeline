"""The SVG reference backend (analysis §3): LIR -> frame.svg, and frame.png through cairosvg.

It is the first backend and the reference the others are compared with: a
fast preview for the agent, a check that the IR really is library-free, and
the golden image Manim's output is diffed against (step 16).

It draws every LIR feature except typesetting TeX itself: a formula is drawn
from its glyph outlines, which the front-end will provide (step 10).

Settings, in pipeline.toml:

    [options.render.svg]
    png = true     # also rasterize frame.svg to frame.png
"""

from pathlib import Path

from irpipe.backends.base import (
    BACKENDS,
    E_ENVIRONMENT,
    Backend,
    Capability,
    Rendered,
)
from irpipe.backends.svg.raster import svg_to_png
from irpipe.backends.svg.writer import to_svg
from irpipe.core import Issue
from irpipe.schema.base import StrictModel
from irpipe.schema.lir import LIRDocument


class SvgOptions(StrictModel):
    png: bool = True


@BACKENDS.register
class SvgBackend(Backend):
    name = "svg"
    capabilities = frozenset(Capability) - {Capability.MATH}
    options_model = SvgOptions

    def render(self, lir: LIRDocument, out_dir: Path) -> Rendered:
        svg = to_svg(lir)
        svg_file = out_dir / "frame.svg"
        svg_file.write_text(svg, encoding="utf-8")
        files, issues = [svg_file], list[Issue]()
        if self.settings.png:
            png_file = out_dir / "frame.png"
            try:
                svg_to_png(svg, png_file, lir.canvas.pixels)
                files.append(png_file)
            except (ImportError, OSError) as exc:
                issues.append(
                    E_ENVIRONMENT(
                        f"frame.png could not be made: {exc}",
                        hint='install the svg extra: pip install -e ".[svg]"',
                    )
                )
        return Rendered(tuple(files), tuple(issues))

    @property
    def settings(self) -> SvgOptions:
        assert isinstance(self.options, SvgOptions)
        return self.options
