"""Check "fill_overlap": filled shapes do not partly overlap by accident (analysis §2.6, §5).

Where two fills partly overlap, one hides part of the other, or two
translucent colors mix into a color that belongs to no concept and depends
on drawing order. If the overlap means something, it should be painted as a
region of its own. Not reported: related objects (one placed by or built
from the other, or in the same group), fills that only touch, and a fill
lying (almost) wholly inside another, which is plain layering.
"""

from collections.abc import Iterable
from itertools import combinations
from typing import Final

import shapely
from shapely.geometry.base import BaseGeometry

from irpipe.checks.base import CHECKS, Check
from irpipe.checks.picture import Picture
from irpipe.core import ISSUE_CODES, Issue, IssueCode, Origin
from irpipe.schema import lir

W_FILL_OVERLAP = ISSUE_CODES.register(
    IssueCode("W-FILL-OVERLAP", Origin.IR, "two filled shapes partly overlap", allowable=True)
)

TOUCH: Final = 0.02
"""Below this share of the smaller fill, the two only touch."""
INSIDE: Final = 0.98
"""Above this share of the smaller fill, it lies inside the other."""


@CHECKS.register
class FillOverlap(Check):
    name = "fill_overlap"
    codes = (W_FILL_OVERLAP,)

    def check(self, picture: Picture) -> Iterable[Issue]:
        fills: dict[str, list[BaseGeometry]] = {}
        for drawn in picture.drawn:
            if isinstance(drawn.item, lir.PathItem) and drawn.item.fill and drawn.fill is not None:
                fills.setdefault(drawn.owner, []).append(drawn.fill)
        areas = {owner: shapely.union_all(parts) for owner, parts in fills.items()}
        for (first, a), (second, b) in combinations(areas.items(), 2):
            smaller = min(a.area, b.area)
            if smaller <= 0 or picture.related(first, second):
                continue
            shared = a.intersection(b).area
            if not TOUCH < shared / smaller < INSIDE:
                continue
            yield W_FILL_OVERLAP(
                f"the fills of '{first}' and '{second}' partly overlap ({shared:.2f} square units)",
                path=picture.path(second),
                objects=[first, second],
                hint="if the overlap means something, paint it as a region of its own "
                f'({{"intersection": ["{first}", "{second}"]}}); otherwise move them apart, '
                "or allow it",
            )
