"""The frame in numbers: units, pixels, safe area and subtitle band (analysis §2.1, §2.2).

The short side of every frame is 9 units, the origin is at the center and y
points up. At the reference size (short side 1080 px) one unit is 120 px:

    canvas = Canvas.from_profile(RenderProfile(aspect="4:5"))
    canvas.units             # (9.0, 11.25)
    canvas.pixels            # (1080, 1350)
    canvas.safe              # Box(x0=-4.1, y0=-5.225, x1=4.1, y1=5.225)

Pixel sizes are rounded *up* to an even number: video encoders reject odd
sizes, and rounding up keeps the frame at least as wide as its ratio. The
units are then read off the rounded reference size, so units x 120 is the
reference pixel size exactly. A higher output resolution only changes how
many pixels a unit is; the units never change, so an IR draws the same
picture at 1080p and at 4K.

Every scale factor is derived from these two constants, never written out.
"""

import math
from dataclasses import dataclass
from fractions import Fraction

from irpipe.core import Registry
from irpipe.platforms import PLATFORMS, Platform
from irpipe.schema.render_profile import Aspect, RenderProfile, SubtitleMode

SHORT_SIDE_UNITS = 9
REFERENCE_SHORT_SIDE_PX = 1080
REFERENCE_PX_PER_UNIT = REFERENCE_SHORT_SIDE_PX // SHORT_SIDE_UNITS  # 120


@dataclass(frozen=True)
class Box:
    """An axis-aligned rectangle in units: left, bottom, right, top."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


def units(reference_px: float) -> float:
    """A length in reference pixels, in units (``units(120) == 1``)."""
    return reference_px / REFERENCE_PX_PER_UNIT


def even_ceil(value: Fraction) -> int:
    """The smallest even integer that is at least ``value``."""
    n = math.ceil(value)
    return n + n % 2


def frame_pixels(aspect: Aspect, short_side_px: int) -> tuple[int, int]:
    """Width and height in pixels for ``aspect`` at a short side of ``short_side_px``."""
    if aspect.ratio >= 1:
        return even_ceil(short_side_px * aspect.ratio), short_side_px
    return short_side_px, even_ceil(short_side_px / aspect.ratio)


@dataclass(frozen=True)
class Canvas:
    """The geometry of one frame, computed from a render profile."""

    aspect: Aspect
    platform: Platform
    units: tuple[float, float]
    reference_pixels: tuple[int, int]
    pixels: tuple[int, int]
    px_per_unit: float
    bounds: Box
    safe: Box
    subtitle_band: Box | None

    @classmethod
    def from_profile(
        cls, profile: RenderProfile, platforms: Registry[Platform] = PLATFORMS
    ) -> "Canvas":
        aspect = profile.aspect_ratio
        platform = platforms.get(profile.platform)
        if platform.aspect is not None and Aspect.parse(platform.aspect).ratio != aspect.ratio:
            raise ValueError(
                f"platform '{platform.name}' shows {platform.aspect} pictures full screen, "
                f"and its overlays are measured on that aspect; got {profile.aspect}"
            )

        ref_w, ref_h = frame_pixels(aspect, REFERENCE_SHORT_SIDE_PX)
        width, height = ref_w / REFERENCE_PX_PER_UNIT, ref_h / REFERENCE_PX_PER_UNIT
        scale = Fraction(profile.resolution, REFERENCE_SHORT_SIDE_PX)
        pixels = (even_ceil(ref_w * scale), even_ceil(ref_h * scale))
        bounds = Box(-width / 2, -height / 2, width / 2, height / 2)

        margins, overlays = profile.margins, platform.overlays
        x0 = bounds.x0 + units(margins.left + overlays.left)
        x1 = bounds.x1 - units(margins.right + overlays.right)
        top = bounds.y1 - units(margins.top + overlays.top)
        bottom = bounds.y0 + units(margins.bottom + overlays.bottom)

        band = None
        if profile.subtitle.mode is not SubtitleMode.NONE:
            band = Box(x0, bottom, x1, bottom + units(subtitle_band_height(profile)))
            bottom = band.y1

        safe = Box(x0, bottom, x1, top)
        if safe.width <= 0 or safe.height <= 0:
            raise ValueError(
                f"margins, platform overlays and subtitle band leave no safe area on a "
                f"{profile.aspect} frame ({safe.width:.2f} x {safe.height:.2f} units)"
            )
        return cls(
            aspect=aspect,
            platform=platform,
            units=(width, height),
            reference_pixels=(ref_w, ref_h),
            pixels=pixels,
            px_per_unit=profile.resolution / SHORT_SIDE_UNITS,
            bounds=bounds,
            safe=safe,
            subtitle_band=band,
        )

    def to_pixels(self, x: float, y: float) -> tuple[float, float]:
        """A point in units as output pixels: origin top left, y down."""
        w, h = self.pixels
        return w / 2 + x * self.px_per_unit, h / 2 - y * self.px_per_unit


def subtitle_band_height(profile: RenderProfile) -> float:
    """Lines x line spacing x caption size, plus one caption size of padding; reference px."""
    caption = profile.typography.sizes().caption
    subtitle = profile.subtitle
    return subtitle.lines * subtitle.line_spacing * caption + caption
