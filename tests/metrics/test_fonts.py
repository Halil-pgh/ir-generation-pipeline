"""fonts: what fontconfig knows about a family (skipped without fontconfig)."""

import shutil

import pytest

from irpipe.metrics import fonts

needs_fontconfig = pytest.mark.skipif(
    shutil.which("fc-match") is None, reason="fontconfig is not installed"
)


@needs_fontconfig
def test_a_family_that_is_not_installed_is_told_apart_from_its_substitute() -> None:
    assert not fonts.installed("No Such Family Anywhere")


@needs_fontconfig
def test_characters_the_font_lacks_are_listed_once_and_spaces_never() -> None:
    lacking = fonts.missing("DejaVu Sans", "ab \U000f0000 \U000f0000")  # a private-use character
    assert lacking == ["\U000f0000"]


def test_without_fontconfig_nothing_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("irpipe.metrics.fonts.shutil.which", lambda _: None)
    fonts._charset.cache_clear()
    try:
        assert fonts.missing("Some Font", "\U000f0000") == []
    finally:
        fonts._charset.cache_clear()
