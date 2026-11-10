"""Check "text_overlap": no two texts or formulas overlap.

Text over text cannot be read, so this is checked whatever relates the two
(analysis §5). Boxes are the measured ones: a text's font box, a formula's
ink box; boxes that only touch do not overlap.
"""

from collections.abc import Iterable
from itertools import combinations
from typing import Final

from irpipe.checks.base import CHECKS, Check
from irpipe.checks.picture import Picture
from irpipe.core import ISSUE_CODES, Issue, IssueCode, Origin

W_TEXT_OVERLAP = ISSUE_CODES.register(
    IssueCode("W-TEXT-OVERLAP", Origin.IR, "two texts or formulas overlap", allowable=True)
)

TOUCH: Final = 1e-4
"""Square units of overlap below which boxes only touch."""


@CHECKS.register
class TextOverlap(Check):
    name = "text_overlap"
    codes = (W_TEXT_OVERLAP,)

    def check(self, picture: Picture) -> Iterable[Issue]:
        for below, above in combinations(picture.texts, 2):
            assert below.fill is not None and above.fill is not None
            shared = below.fill.intersection(above.fill)
            if shared.area <= TOUCH:
                continue
            x0, y0, x1, y1 = shared.bounds
            yield W_TEXT_OVERLAP(
                f"'{below.owner}' and '{above.owner}' overlap "
                f"({x1 - x0:.2f} x {y1 - y0:.2f} units)",
                path=picture.path(above.owner),
                objects=[below.owner, above.owner],
                hint="move one of them; next_to or a stack keeps texts apart",
            )
