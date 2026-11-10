"""Check "offscreen": nothing reaches past the edge of the frame.

What runs off the frame is cut off in the picture. Strokes count at their
width; a line that ends exactly on the edge is fine. Some lines are meant
to run off (an axis drawn edge to edge): allow those.
"""

from collections.abc import Iterable

from irpipe.checks.base import CHECKS, Check
from irpipe.checks.picture import Picture, beyond, reach_of
from irpipe.core import ISSUE_CODES, Issue, IssueCode, Origin

W_OFFSCREEN = ISSUE_CODES.register(
    IssueCode(
        "W-OFFSCREEN", Origin.IR, "an object reaches past the edge of the frame", allowable=True
    )
)


def sides(past: list[tuple[str, float]], what: str) -> str:
    """``[("right", 0.4)]`` -> "0.40 past the right edge of <what>"."""
    return ", ".join(f"{amount:.2f} past the {side} edge of {what}" for side, amount in past)


@CHECKS.register
class Offscreen(Check):
    name = "offscreen"
    codes = (W_OFFSCREEN,)

    def check(self, picture: Picture) -> Iterable[Issue]:
        for owner, drawn in picture.by_owner().items():
            past = beyond(reach_of(drawn), picture.frame)
            if past:
                yield W_OFFSCREEN(
                    f"'{owner}' reaches {sides(past, 'the frame')}",
                    path=picture.path(owner),
                    objects=[owner],
                    hint="move it in or make it smaller; allow it if it is meant to run off "
                    "the edge",
                )
