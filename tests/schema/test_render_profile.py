"""RenderProfile: what is accepted, what is refused, and the defaults."""

from fractions import Fraction

import pytest
from pydantic import ValidationError

from irpipe.schema.render_profile import (
    DEFAULT_MARGIN,
    SCALE_PRESETS,
    Insets,
    RenderProfile,
    RoleSizes,
    SubtitleMode,
)


def test_only_the_aspect_is_required() -> None:
    profile = RenderProfile(aspect="16:9")
    assert profile.resolution == 1080
    assert profile.platform == "plain"
    assert profile.margins == Insets.uniform(DEFAULT_MARGIN)
    assert profile.subtitle.mode is SubtitleMode.NONE
    assert profile.typography.lang == "en"
    assert profile.typography.font_pair.text == "Inter"


@pytest.mark.parametrize(
    ("text", "ratio"),
    [
        ("16:9", Fraction(16, 9)),
        ("1.91:1", Fraction(191, 100)),
        (" 7:5 ", Fraction(7, 5)),
        ("2.35:1", Fraction(47, 20)),
    ],
)
def test_any_w_h_aspect_is_exact(text: str, ratio: Fraction) -> None:
    assert RenderProfile(aspect=text).aspect_ratio.ratio == ratio


def test_the_print_preset_is_one_to_root_two() -> None:
    aspect = RenderProfile(aspect="1:√2").aspect_ratio
    assert aspect.is_portrait
    assert float(aspect.ratio) == pytest.approx(2**-0.5)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("16x9", "written W:H"),
        ("0:9", "zero side"),
        ("5:1", "outside the supported range"),
        ("1:4.5", "outside the supported range"),
    ],
)
def test_a_bad_aspect_is_refused(text: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        RenderProfile(aspect=text)


@pytest.mark.parametrize(("resolution", "message"), [(1081, "even"), (240, "greater than")])
def test_the_resolution_is_an_even_short_side(resolution: int, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        RenderProfile(aspect="16:9", resolution=resolution)


def test_a_misspelled_field_is_refused() -> None:
    with pytest.raises(ValidationError, match="subtitles"):
        RenderProfile.model_validate({"aspect": "16:9", "subtitles": {"mode": "reserve"}})


def test_the_comfortable_scale_is_the_analysis_example() -> None:
    sizes = RenderProfile(aspect="16:9").typography.sizes()
    assert sizes == RoleSizes(title=64, heading=52, body=42, label=38, caption=34)


@pytest.mark.parametrize("preset", ["compact", "comfortable", "large"])
def test_every_preset_grows_from_caption_to_title(preset: str) -> None:
    s = SCALE_PRESETS[preset]
    assert s.caption < s.label < s.body < s.heading < s.title


def test_a_modular_scale_steps_by_its_ratio() -> None:
    profile = RenderProfile.model_validate(
        {"aspect": "16:9", "typography": {"scale": {"base": 40, "ratio": 1.25}}}
    )
    sizes = profile.typography.sizes()
    assert (sizes.title, sizes.heading, sizes.body, sizes.label, sizes.caption) == pytest.approx(
        (62.5, 50, 40, 32, 25.6)
    )


@pytest.mark.parametrize("lang", ["en", "tr", "pt-BR"])
def test_a_language_tag_is_accepted(lang: str) -> None:
    assert RenderProfile.model_validate({"aspect": "16:9", "typography": {"lang": lang}})


def test_a_language_name_is_not_a_tag() -> None:
    with pytest.raises(ValidationError, match="lang"):
        RenderProfile.model_validate({"aspect": "16:9", "typography": {"lang": "english"}})


def test_the_subtitle_has_one_to_four_lines() -> None:
    with pytest.raises(ValidationError, match="lines"):
        RenderProfile.model_validate({"aspect": "16:9", "subtitle": {"lines": 5}})


def test_a_profile_survives_json_and_has_a_schema() -> None:
    profile = RenderProfile.model_validate(
        {"aspect": "9:16", "platform": "tiktok", "subtitle": {"mode": "burn_in"}}
    )
    assert RenderProfile.model_validate_json(profile.model_dump_json()) == profile
    assert "aspect" in RenderProfile.model_json_schema()["required"]
