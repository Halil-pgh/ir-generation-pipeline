"""Colors: two ways to write a literal color, no alpha."""

import pytest
from pydantic import TypeAdapter, ValidationError

from irpipe.schema.color import Color, Mix, to_rgb
from irpipe.schema.render_profile import RenderProfile

COLOR = TypeAdapter(Color)


@pytest.mark.parametrize("color", ["#FFD43B", "#ffd43b", [255, 212, 59]])
def test_hex_and_channels_are_the_same_color(color: object) -> None:
    assert to_rgb(COLOR.validate_python(color)) == (255, 212, 59)


@pytest.mark.parametrize("color", ["#FFD43BAA", "FFD43B", "yellow", [255, 212], [-1, 0, 0]])
def test_anything_else_is_refused(color: object) -> None:
    with pytest.raises(ValidationError):
        COLOR.validate_python(color)


def test_a_mix_takes_exactly_two_colors() -> None:
    Mix(mix=("a", "#FFFFFF"))
    with pytest.raises(ValidationError):
        Mix.model_validate({"mix": ["a", "b", "c"]})


def test_the_theme_background_takes_either_form() -> None:
    profile = RenderProfile.model_validate({"aspect": "1:1", "theme": {"background": [14, 17, 23]}})
    assert to_rgb(profile.theme.background) == (14, 17, 23)
