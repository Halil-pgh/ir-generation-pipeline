"""Canvas: units, pixels, safe area and subtitle band of a frame."""

import pytest

from irpipe.canvas import REFERENCE_PX_PER_UNIT, Canvas, units
from irpipe.core import UnknownPluginError
from irpipe.schema.render_profile import ASPECT_PRESETS, RenderProfile

# The analysis's table (§2.1): aspect, pixels at a 1080 px short side, units.
ANALYSIS_TABLE = [
    ("16:9", (1920, 1080), (16, 9)),
    ("9:16", (1080, 1920), (9, 16)),
    ("4:3", (1440, 1080), (12, 9)),
    ("3:4", (1080, 1440), (9, 12)),
    ("1:1", (1080, 1080), (9, 9)),
    ("4:5", (1080, 1350), (9, 11.25)),
    ("3:2", (1620, 1080), (13.5, 9)),
    ("2:3", (1080, 1620), (9, 13.5)),
    ("16:10", (1728, 1080), (14.4, 9)),
    ("21:9", (2520, 1080), (21, 9)),
    ("1.91:1", (2064, 1080), (17.2, 9)),
    ("1:√2", (1080, 1528), (9, 12.73)),
]

RESOLUTIONS = [720, 1080, 1440, 2160]
OTHER_ASPECTS = ["7:5", "2.35:1", "1:3.3", "5:4"]


def canvas(aspect: str, **profile: object) -> Canvas:
    return Canvas.from_profile(RenderProfile.model_validate({"aspect": aspect, **profile}))


# Units and pixels


@pytest.mark.parametrize(("aspect", "pixels", "size"), ANALYSIS_TABLE)
def test_the_analysis_table_holds(
    aspect: str, pixels: tuple[int, int], size: tuple[float, float]
) -> None:
    c = canvas(aspect)
    assert c.pixels == pixels
    assert c.units == pytest.approx(size, abs=0.005)  # the table shows two decimals


def test_the_table_covers_every_preset() -> None:
    assert [row[0] for row in ANALYSIS_TABLE] == list(ASPECT_PRESETS)


@pytest.mark.parametrize("resolution", RESOLUTIONS)
@pytest.mark.parametrize("aspect", [*ASPECT_PRESETS, *OTHER_ASPECTS])
def test_pixels_are_even(aspect: str, resolution: int) -> None:
    width, height = canvas(aspect, resolution=resolution).pixels
    assert width % 2 == 0
    assert height % 2 == 0


@pytest.mark.parametrize("aspect", [*ASPECT_PRESETS, *OTHER_ASPECTS])
def test_units_times_120_is_the_reference_size(aspect: str) -> None:
    c = canvas(aspect)
    width, height = c.units
    assert (width * REFERENCE_PX_PER_UNIT, height * REFERENCE_PX_PER_UNIT) == pytest.approx(
        c.reference_pixels
    )
    assert min(c.units) == 9


@pytest.mark.parametrize("resolution", RESOLUTIONS)
def test_the_resolution_changes_pixels_but_never_units(resolution: int) -> None:
    reference, scaled = canvas("1:√2"), canvas("1:√2", resolution=resolution)
    assert scaled.units == reference.units
    assert scaled.px_per_unit == resolution / 9
    assert min(scaled.pixels) == resolution


def test_4k_doubles_every_pixel_size() -> None:
    assert canvas("1.91:1", resolution=2160).pixels == (4128, 2160)


def test_the_origin_is_the_center_and_y_points_up() -> None:
    c = canvas("16:9")
    assert c.to_pixels(0, 0) == (960, 540)
    assert c.to_pixels(c.bounds.x0, c.bounds.y1) == (0, 0)  # top left
    assert c.to_pixels(c.bounds.x1, c.bounds.y0) == (1920, 1080)  # bottom right


# Safe area and subtitle band


def test_without_subtitles_the_safe_area_is_the_frame_minus_margins() -> None:
    c = canvas("4:5")
    assert c.subtitle_band is None
    margin = units(48)
    assert (c.safe.x0, c.safe.y0, c.safe.x1, c.safe.y1) == pytest.approx(
        (-4.5 + margin, -5.625 + margin, 4.5 - margin, 5.625 - margin)
    )


@pytest.mark.parametrize("mode", ["reserve", "burn_in"])
def test_the_band_sits_on_the_bottom_margin_and_ends_the_safe_area(mode: str) -> None:
    c = canvas("16:9", subtitle={"mode": mode, "lines": 2})
    band = c.subtitle_band
    assert band is not None
    assert band.y0 == pytest.approx(-4.5 + units(48))
    assert band.height == pytest.approx(units(2 * 1.2 * 34 + 34))  # comfortable caption: 34 px
    assert (band.x0, band.x1) == (c.safe.x0, c.safe.x1)
    assert c.safe.y0 == band.y1


def test_more_lines_make_a_taller_band() -> None:
    one = canvas("16:9", subtitle={"mode": "reserve", "lines": 1}).subtitle_band
    three = canvas("16:9", subtitle={"mode": "reserve", "lines": 3}).subtitle_band
    assert one is not None and three is not None
    assert three.height - one.height == pytest.approx(units(2 * 1.2 * 34))


def test_on_a_vertical_platform_the_band_goes_above_its_interface() -> None:
    c = canvas("9:16", platform="tiktok", subtitle={"mode": "reserve"})
    band = c.subtitle_band
    assert band is not None
    assert band.y0 == pytest.approx(-8 + units(48 + 480))  # margin + TikTok's bottom overlay
    assert c.safe.x1 == pytest.approx(4.5 - units(48 + 120))  # the button column on the right
    assert c.safe.y1 == pytest.approx(8 - units(48 + 220))


def test_a_platform_with_overlays_keeps_its_aspect() -> None:
    with pytest.raises(ValueError, match="'tiktok' shows 9:16 pictures full screen"):
        canvas("16:9", platform="tiktok")


def test_margins_that_leave_no_room_are_refused() -> None:
    with pytest.raises(ValueError, match="leave no safe area"):
        canvas("1:1", margins={"top": 600, "bottom": 600})


def test_an_unknown_platform_gets_a_suggestion() -> None:
    with pytest.raises(UnknownPluginError, match="did you mean 'tiktok'"):
        canvas("9:16", platform="tiktk")
