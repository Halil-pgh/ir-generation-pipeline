"""Check "text_crossed": no line runs through a text or formula.

A line through a text makes it hard to read, whether it is drawn over the
text or under it, and whatever relates the two (analysis §5): a label set
on the middle of its own line is reported too. The text's box is taken a
little smaller at the top and bottom, where a font box is mostly empty,
so a line that grazes it does not count.
"""

from collections.abc import Iterable
from typing import Final

from shapely.geometry import JOIN_STYLE

from irpipe.checks.base import CHECKS, Check
from irpipe.checks.picture import Picture
from irpipe.core import ISSUE_CODES, Issue, IssueCode, Origin

W_TEXT_CROSSED = ISSUE_CODES.register(
    IssueCode("W-TEXT-CROSSED", Origin.IR, "a line runs through a text or formula", allowable=True)
)

INSET: Final = 0.1
"""Share of a text's height taken off its box all round before lines are looked for."""
LONGEST_GRAZE: Final = 0.02
"""Units of a line inside the box that still count as a graze."""


@CHECKS.register
class TextCrossed(Check):
    name = "text_crossed"
    codes = (W_TEXT_CROSSED,)

    def check(self, picture: Picture) -> Iterable[Issue]:
        lines = [d for d in picture.drawn if d.line is not None]
        for text in picture.texts:
            assert text.fill is not None
            _, y0, _, y1 = text.reach
            inner = text.fill.buffer(-INSET * (y1 - y0), join_style=JOIN_STYLE.mitre)
            crossing: dict[str, float] = {}
            for drawn in lines:
                assert drawn.line is not None
                if drawn.owner == text.owner:
                    continue
                inside = drawn.line.intersection(inner).length
                if inside > LONGEST_GRAZE:
                    crossing[drawn.owner] = crossing.get(drawn.owner, 0.0) + inside
            for owner, length in crossing.items():
                yield W_TEXT_CROSSED(
                    f"a line of '{owner}' runs through '{text.owner}' "
                    f"({length:.2f} units inside its box)",
                    path=picture.path(text.owner),
                    objects=[text.owner, owner],
                    hint="move the text off the line (dir and gap set it beside a point), "
                    "or the line away from the text",
                )
