"""Platforms: the interface each app draws over the picture."""

from irpipe.canvas import Canvas
from irpipe.core import Registry
from irpipe.platforms import PLATFORMS, Platform
from irpipe.schema.render_profile import Insets, RenderProfile


def test_plain_covers_nothing_and_takes_any_aspect() -> None:
    plain = PLATFORMS.get("plain")
    assert plain.overlays == Insets()
    assert plain.aspect is None


def test_vertical_social_covers_on_each_side_the_most_of_the_three_apps() -> None:
    apps = [PLATFORMS.get(n) for n in ("tiktok", "instagram_reels", "youtube_shorts")]
    widest = PLATFORMS.get("vertical_social").overlays
    for side in ("top", "right", "bottom", "left"):
        assert getattr(widest, side) == max(getattr(app.overlays, side) for app in apps)


def test_a_new_platform_is_one_registration() -> None:
    platforms: Registry[Platform] = Registry("platform", key=lambda p: p.name)
    platforms.register(
        Platform("kiosk", "a kiosk with a clock bar on top", Insets(top=60), aspect="16:9")
    )
    profile = RenderProfile(aspect="16:9", platform="kiosk")
    canvas = Canvas.from_profile(profile, platforms=platforms)
    assert canvas.safe.y1 == 4.5 - (48 + 60) / 120
