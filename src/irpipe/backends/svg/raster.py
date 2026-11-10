"""SVG -> PNG through cairosvg (the ``svg`` extra).

Cairo draws the text with the fonts installed on this machine, found by
fontconfig. cairosvg is imported only here, when a PNG is wanted, so the
SVG backend works without it and only frame.png is lost.
"""

from pathlib import Path


def svg_to_png(svg: str, path: Path, size: tuple[int, int]) -> None:
    """Rasterize ``svg`` to ``path`` at ``size`` pixels.

    Raises ImportError or OSError when cairosvg or the Cairo library is missing.
    """
    import cairosvg  # type: ignore[import-untyped]

    width, height = size
    cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        write_to=str(path),
        output_width=width,
        output_height=height,
    )
