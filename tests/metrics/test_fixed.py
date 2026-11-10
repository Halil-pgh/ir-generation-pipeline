"""The fixed text measurer and the provider registry."""

import pytest

from irpipe.core import PluginDefinitionError
from irpipe.metrics import METRICS, TextBox, TextMetrics
from irpipe.metrics.fixed import FixedMetrics


def measure(text: str, weight: str = "regular") -> TextBox:
    return FixedMetrics().text(text, font="Inter", size=40, weight=weight, italic=False)  # type: ignore[arg-type]


def test_every_glyph_is_as_wide_as_the_next() -> None:
    assert measure("ab").width == 2 * measure("a").width == 2 * 40 * 0.55


def test_bold_is_a_little_wider() -> None:
    assert measure("ab", "bold").width > measure("ab").width


def test_ascent_and_descent_are_shares_of_the_size() -> None:
    box = measure("x")
    assert (box.ascent, box.descent, box.height) == (30, 10, 40)


def test_the_provider_is_registered_by_name() -> None:
    assert METRICS.get("fixed") is FixedMetrics


def test_a_provider_needs_a_name() -> None:
    class Nameless(TextMetrics):
        def text(self, *args: object, **kwargs: object) -> TextBox:
            return TextBox(0, 0, 0)

    with pytest.raises(PluginDefinitionError, match="needs a `name`"):
        METRICS.register(Nameless)
