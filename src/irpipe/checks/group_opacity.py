"""Check "group_opacity": a faded group's children do not overlap (analysis §2.4).

A group's opacity is multiplied into each child (SEMANTICS.md), not laid on
the group as one layer, so where faded children overlap they show through
each other. That is usually not what was meant, and libraries that fade a
group as one layer would draw it differently.
"""

from collections.abc import Iterable
from itertools import combinations
from typing import Final

import shapely

from irpipe.checks.base import CHECKS, Check
from irpipe.checks.picture import Picture
from irpipe.core import ISSUE_CODES, Issue, IssueCode, Origin
from irpipe.schema.ir import Container

W_GROUP_OPACITY = ISSUE_CODES.register(
    IssueCode(
        "W-GROUP-OPACITY",
        Origin.IR,
        "a faded group's children overlap and show through each other",
        allowable=True,
    )
)

TOUCH: Final = 1e-4
"""Square units of overlap below which children only touch."""


@CHECKS.register
class GroupOpacity(Check):
    name = "group_opacity"
    codes = (W_GROUP_OPACITY,)

    def check(self, picture: Picture) -> Iterable[Issue]:
        drawn = picture.by_owner()
        for group in picture.document.objects:
            if not isinstance(group, Container) or (group.opacity or 1) >= 1:
                continue
            covered = {
                child: shapely.union_all(
                    [
                        d.ink
                        for oid in (child, *picture.descendants(child))
                        for d in drawn.get(oid, [])
                    ]
                )
                for child in group.children
            }
            for first, second in combinations(group.children, 2):
                if covered[first].intersection(covered[second]).area > TOUCH:
                    yield W_GROUP_OPACITY(
                        f"group '{group.id}' is faded to {group.opacity:.0%}, and its children "
                        f"'{first}' and '{second}' overlap; each child is faded on its own, "
                        "so they show through each other",
                        path=picture.path(group.id),
                        objects=[group.id, first, second],
                        hint="fade each child as you want it, or keep the children apart; "
                        "allow it if the see-through look is meant",
                    )
                    break
