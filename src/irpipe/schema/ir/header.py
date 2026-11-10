"""The IR header: what the orchestrator decides and the agent may not change (analysis §1).

The orchestrator writes the header from the brief and its render profile:
the intent sentence, the frame (aspect, pixels, units, safe area, subtitle
band), the resolved typography, the concept colors, the style classes and
the theme's defaults.
The agent only writes the body (document.py); a later step checks
with a hash that the header it returns is the one it was given.
"""

import hashlib
import json
from typing import Annotated, Final, Literal, Self

from pydantic import AfterValidator, Field, PositiveFloat, PositiveInt, model_validator

from irpipe.schema.base import StrictModel
from irpipe.schema.color import Color, ColorName, ColorRef
from irpipe.schema.ir.common import Box, Name, Size
from irpipe.schema.ir.objects import Opacity
from irpipe.schema.render_profile import RoleSizes, SubtitleMode, check_aspect

IR_VERSION: Final = "frame-ir/1.0"


class SubtitleHeader(StrictModel):
    """The subtitle setting and, unless the mode is ``none``, the band it keeps."""

    mode: SubtitleMode
    lines: int = Field(ge=1, le=4)
    band: Box | None = None

    @model_validator(mode="after")
    def _band_matches_mode(self) -> Self:
        if (self.mode is SubtitleMode.NONE) != (self.band is None):
            raise ValueError("a subtitle band is given exactly when the mode is not 'none'")
        return self


class FrameHeader(StrictModel):
    aspect: Annotated[str, AfterValidator(check_aspect)]
    pixels: tuple[PositiveInt, PositiveInt]
    units: tuple[PositiveFloat, PositiveFloat]
    platform: str
    background: Color
    subtitle: SubtitleHeader
    safe: Box


class TypographyHeader(StrictModel):
    lang: str = Field(pattern=r"^[a-z]{2,3}(-[A-Z]{2})?$")
    text_font: str
    math: str
    sizes: RoleSizes


class Style(StrictModel):
    """A style class: any paint or text field, applied to every object that names it."""

    color: ColorRef | None = None
    fill: ColorRef | None = None
    fill_opacity: Opacity | None = None
    opacity: Opacity | None = None
    stroke_width: PositiveFloat | None = None
    dash: tuple[PositiveFloat, ...] | None = None
    size: Size | None = None
    weight: Literal["regular", "bold"] | None = None
    italic: bool | None = None


class ThemeHeader(StrictModel):
    """What an object gets when neither it nor its style classes say (analysis §2.8).

    A color left out here is white or black, whichever contrasts more with
    the background.
    """

    text: Color | None = None
    line: Color | None = None
    stroke_width: PositiveFloat = 4


class IRHeader(StrictModel):
    version: Literal["frame-ir/1.0"] = IR_VERSION
    intent: str = Field(min_length=1)
    frame: FrameHeader
    typography: TypographyHeader
    colors: dict[ColorName, Color] = Field(default_factory=dict)
    styles: dict[Name, Style] = Field(default_factory=dict)
    theme: ThemeHeader = Field(default_factory=ThemeHeader)


def header_hash(header: IRHeader) -> str:
    """SHA-256 of the header's content, the same however the JSON was spaced or ordered.

    The header is hashed after validation, so ``9`` and ``9.0``, key order
    and whitespace do not matter; only what the header says does.
    """
    canonical = json.dumps(
        header.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
