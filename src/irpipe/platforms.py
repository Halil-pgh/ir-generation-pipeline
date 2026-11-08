"""Where a picture is shown, and how much of it the app's interface covers.

On TikTok, Reels and Shorts the app draws buttons, captions and the account
name over the picture. Those parts of the frame are not safe for content.
A ``Platform`` records them as insets in reference pixels of a 1080x1920
frame; the canvas subtracts them, together with the margins, from the safe
area and puts the subtitle band above them.

Adding a platform is one ``PLATFORMS.register(Platform(...))`` call, in this
file or in a plugin package.

The overlay figures are approximate. The platforms publish no official
numbers for organic posts, and third-party guides disagree, so each side
takes the larger figure of these two guides (read on 9 Nov 2026):

- https://adaptlypost.com/blog/social-media-safe-zones-2026-complete-guide
- https://wildandfreetools.com/blog/vertical-video-safe-zones-guide-2026/
"""

from dataclasses import dataclass, field

from irpipe.core import Registry
from irpipe.schema.render_profile import Insets


@dataclass(frozen=True)
class Platform:
    """A place pictures are shown.

    ``overlays`` is the part of the frame the app covers, in reference px.
    ``aspect`` is the aspect the app shows full screen; a platform with
    overlays only accepts that aspect, since its overlays are measured on it.
    """

    name: str
    description: str
    overlays: Insets = field(default_factory=Insets)
    aspect: str | None = None


PLATFORMS: Registry[Platform] = Registry("platform", key=lambda platform: platform.name)

PLATFORMS.register(
    Platform("plain", "nothing drawn over the picture: YouTube, slides, print, feed posts")
)
TIKTOK = PLATFORMS.register(
    Platform(
        "tiktok",
        "TikTok, full screen",
        Insets(top=220, right=120, bottom=480, left=60),
        aspect="9:16",
    )
)
INSTAGRAM_REELS = PLATFORMS.register(
    Platform(
        "instagram_reels",
        "Instagram Reels, full screen",
        Insets(top=220, right=84, bottom=450, left=0),
        aspect="9:16",
    )
)
YOUTUBE_SHORTS = PLATFORMS.register(
    Platform(
        "youtube_shorts",
        "YouTube Shorts, full screen",
        Insets(top=150, right=96, bottom=400, left=0),
        aspect="9:16",
    )
)


def widest(name: str, description: str, *platforms: Platform) -> Platform:
    """A platform whose overlays cover, on each side, the most any of ``platforms`` covers."""
    sides = ("top", "right", "bottom", "left")
    overlays = Insets(**{s: max(getattr(p.overlays, s) for p in platforms) for s in sides})
    return Platform(name, description, overlays, aspect=platforms[0].aspect)


PLATFORMS.register(
    widest(
        "vertical_social",
        "one 9:16 file for TikTok, Reels and Shorts alike",
        TIKTOK,
        INSTAGRAM_REELS,
        YOUTUBE_SHORTS,
    )
)
