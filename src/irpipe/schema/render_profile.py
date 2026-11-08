"""What the picture is rendered for: the render profile (analysis §2.1, §2.2, §2.5).

    {"aspect": "9:16", "resolution": 1080, "platform": "tiktok",
     "subtitle": {"mode": "reserve", "lines": 2},
     "typography": {"scale": "comfortable", "lang": "en"}}

The planner chooses a profile; the orchestrator turns it into the locked
header of the IR with the help of ``Canvas`` (irpipe/canvas.py), which does
all the arithmetic. This module only describes and validates the choice.

Lengths here are in *reference pixels*: pixels of the picture when its short
side is 1080 px, whatever the real output resolution is. Margins, platform
overlays and type sizes are therefore the same numbers at 1080p and at 4K.
"""

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, Field

from irpipe.schema.base import StrictModel
from irpipe.schema.color import Color

MIN_RATIO = Fraction(1, 4)
MAX_RATIO = Fraction(4, 1)

_RATIO_FORMAT = re.compile(r"(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)")


@dataclass(frozen=True)
class Aspect:
    """A width:height ratio, kept exact (``1.91:1`` is 191/100, not a float)."""

    name: str
    width: Fraction
    height: Fraction

    @property
    def ratio(self) -> Fraction:
        return self.width / self.height

    @property
    def is_portrait(self) -> bool:
        return self.width < self.height

    @classmethod
    def parse(cls, text: str) -> "Aspect":
        """A preset name (``1:√2``) or any ``W:H`` with decimals, between 1:4 and 4:1."""
        text = text.strip()
        preset = ASPECT_PRESETS.get(text)
        if preset is not None:
            return preset.aspect
        match = _RATIO_FORMAT.fullmatch(text)
        if match is None:
            raise ValueError(f"an aspect is written W:H, such as 16:9 or 1.91:1; got {text!r}")
        width, height = Fraction(match[1]), Fraction(match[2])
        if width == 0 or height == 0:
            raise ValueError(f"an aspect cannot have a zero side; got {text!r}")
        aspect = cls(text, width, height)
        if not MIN_RATIO <= aspect.ratio <= MAX_RATIO:
            raise ValueError(f"aspect {text} is outside the supported range 1:4 to 4:1")
        return aspect


@dataclass(frozen=True)
class AspectPreset:
    aspect: Aspect
    typical_use: str


def _preset(name: str, width: Fraction, height: Fraction, use: str) -> tuple[str, AspectPreset]:
    return name, AspectPreset(Aspect(name, width, height), use)


ASPECT_PRESETS: dict[str, AspectPreset] = dict(
    [
        _preset("16:9", Fraction(16), Fraction(9), "YouTube, presentations"),
        _preset("9:16", Fraction(9), Fraction(16), "Shorts, Reels, TikTok"),
        _preset("4:3", Fraction(4), Fraction(3), "classic slides, tablets"),
        _preset("3:4", Fraction(3), Fraction(4), "tablets in portrait"),
        _preset("1:1", Fraction(1), Fraction(1), "square posts"),
        _preset("4:5", Fraction(4), Fraction(5), "Instagram portrait posts"),
        _preset("3:2", Fraction(3), Fraction(2), "photos"),
        _preset("2:3", Fraction(2), Fraction(3), "Pinterest"),
        _preset("16:10", Fraction(16), Fraction(10), "laptop screens"),
        _preset("21:9", Fraction(21), Fraction(9), "ultra-wide screens"),
        _preset("1.91:1", Fraction("1.91"), Fraction(1), "link preview images"),
        _preset("1:√2", Fraction(1), Fraction(math.sqrt(2)), "A4 worksheets (print)"),
    ]
)
"""The analysis's table of common aspects; any other W:H in range works too."""


def check_aspect(text: str) -> str:
    """Validate an aspect and return it stripped; for models that store the text."""
    Aspect.parse(text)
    return text.strip()


def _check_resolution(value: int) -> int:
    if value % 2:
        raise ValueError(
            f"the short side must be an even number of pixels (video encoders need it), got {value}"
        )
    return value


class Insets(StrictModel):
    """Space on each side of the picture, in reference pixels."""

    top: float = Field(0, ge=0)
    right: float = Field(0, ge=0)
    bottom: float = Field(0, ge=0)
    left: float = Field(0, ge=0)

    @classmethod
    def uniform(cls, value: float) -> Self:
        return cls(top=value, right=value, bottom=value, left=value)


DEFAULT_MARGIN = 48.0
"""Reference px kept free on every side; the analysis's header example uses about 0.4 units."""


class SubtitleMode(StrEnum):
    NONE = "none"  # no band; the whole safe area is for content
    RESERVE = "reserve"  # the band stays empty; subtitles are added later, in the video edit
    BURN_IN = "burn_in"  # the front-end draws the brief's subtitle text into the band


class Subtitle(StrictModel):
    mode: SubtitleMode = SubtitleMode.NONE
    lines: int = Field(2, ge=1, le=4)
    line_spacing: float = Field(1.2, ge=1.0, le=2.0)


class RoleSizes(StrictModel):
    """Type size of each text role, in reference pixels."""

    title: float
    heading: float
    body: float
    label: float
    caption: float


ScalePreset = Literal["compact", "comfortable", "large"]

SCALE_PRESETS: dict[str, RoleSizes] = {
    "comfortable": RoleSizes(title=64, heading=52, body=42, label=38, caption=34),
    "compact": RoleSizes(title=54, heading=44, body=36, label=32, caption=29),
    "large": RoleSizes(title=77, heading=62, body=50, label=46, caption=41),
}
"""``comfortable`` is the analysis's header example; the other two are it times 0.85 and 1.2."""


class ModularScale(StrictModel):
    """A base size and a ratio: each role is one step of the ratio from the next."""

    base: float = Field(gt=0, description="the body size, in reference px")
    ratio: float = Field(gt=1, le=2)

    def sizes(self) -> RoleSizes:
        b, r = self.base, self.ratio
        return RoleSizes(title=b * r * r, heading=b * r, body=b, label=b / r, caption=b / r / r)


class FontPair(StrictModel):
    """A text font and a matching math font; which pairs are allowed is decided later."""

    text: str = "Inter"
    math: str = "latin-modern"


class Typography(StrictModel):
    font_pair: FontPair = Field(default_factory=FontPair)
    scale: ScalePreset | ModularScale = "comfortable"
    lang: str = Field("en", pattern=r"^[a-z]{2,3}(-[A-Z]{2})?$")

    def sizes(self) -> RoleSizes:
        """The size of every text role, in reference pixels."""
        if isinstance(self.scale, ModularScale):
            return self.scale.sizes()
        return SCALE_PRESETS[self.scale]


class Theme(StrictModel):
    background: Color = "#0E1117"


class RenderProfile(StrictModel):
    """Everything about the frame that is decided before any object is drawn."""

    aspect: Annotated[str, AfterValidator(check_aspect)]
    resolution: Annotated[int, Field(ge=360, le=4320), AfterValidator(_check_resolution)] = 1080
    platform: str = "plain"
    margins: Insets = Field(default_factory=lambda: Insets.uniform(DEFAULT_MARGIN))
    subtitle: Subtitle = Field(default_factory=Subtitle)
    typography: Typography = Field(default_factory=Typography)
    theme: Theme = Field(default_factory=Theme)

    @property
    def aspect_ratio(self) -> Aspect:
        return Aspect.parse(self.aspect)
