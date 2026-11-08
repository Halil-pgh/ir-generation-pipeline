"""Colors as contracts write them (analysis §2.4).

A color is ``"#RRGGBB"`` or ``[r, g, b]`` with 0-255 sRGB channels. There is
no alpha: transparency is the separate ``opacity`` field, so it cannot be
said in two ways.

Where an object names a color (``ColorRef``) it may also give the name of a
header color (``"a"``) or ``"none"`` for no paint at all; ``"none"`` is
therefore not allowed as a color name.
"""

from typing import Annotated

from pydantic import AfterValidator, Field

from irpipe.schema.base import StrictModel

HEX_PATTERN = r"^#[0-9A-Fa-f]{6}$"
NAME_PATTERN = r"^[A-Za-z][A-Za-z0-9_]*$"
NO_PAINT = "none"

Channel = Annotated[int, Field(ge=0, le=255)]
RGB = tuple[Channel, Channel, Channel]

Color = Annotated[str, Field(pattern=HEX_PATTERN)] | RGB
"""A literal color."""

ColorRef = Annotated[str, Field(pattern=r"^(#[0-9A-Fa-f]{6}|[A-Za-z][A-Za-z0-9_]*)$")] | RGB
"""A literal color, the name of a header color, or ``"none"``."""


def _not_reserved(name: str) -> str:
    if name == NO_PAINT:
        raise ValueError(f"'{NO_PAINT}' means no paint and cannot name a color")
    return name


ColorName = Annotated[str, Field(pattern=NAME_PATTERN), AfterValidator(_not_reserved)]


class Mix(StrictModel):
    """An extra color mixed from two others, for example the overlap of two concepts."""

    mix: tuple[ColorRef, ColorRef]


def to_rgb(color: Color) -> tuple[int, int, int]:
    """The channels of a literal color."""
    if isinstance(color, str):
        return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    return color
