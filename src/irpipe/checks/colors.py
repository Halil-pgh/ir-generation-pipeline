"""Check "similar_colors": different colors in the picture can be told apart (analysis §2.4).

"One concept, one color" only works when colors that mean different things
look different. Every color something is painted with (fill, stroke, text)
is compared with every other by CIEDE2000; pairs closer than ``min_delta_e``
are reported with the objects that use them. The same color on several
objects is fine: it is one concept.
"""

from collections.abc import Iterable
from itertools import combinations

from pydantic import PositiveFloat

from irpipe import colormath
from irpipe.checks.base import CHECKS, Check
from irpipe.checks.picture import Picture
from irpipe.core import ISSUE_CODES, Issue, IssueCode, Origin
from irpipe.schema import lir
from irpipe.schema.base import StrictModel

W_SIMILAR_COLORS = ISSUE_CODES.register(
    IssueCode(
        "W-SIMILAR-COLORS", Origin.IR, "two colors are too alike to tell apart", allowable=True
    )
)


class SimilarColorsOptions(StrictModel):
    min_delta_e: PositiveFloat = 10
    """CIEDE2000; about 1 is just noticeable side by side, 10 tells apart at a glance."""


@CHECKS.register
class SimilarColors(Check):
    name = "similar_colors"
    codes = (W_SIMILAR_COLORS,)
    options_model = SimilarColorsOptions

    def check(self, picture: Picture) -> Iterable[Issue]:
        users: dict[str, list[str]] = {}
        for drawn in picture.drawn:
            for color in _colors(drawn.item):
                owners = users.setdefault(color, [])
                if drawn.owner not in owners:
                    owners.append(drawn.owner)
        for first, second in combinations(users, 2):
            difference = colormath.delta_e(
                colormath.lab(colormath.rgb(first)), colormath.lab(colormath.rgb(second))
            )
            if difference >= self.options.min_delta_e:
                continue
            a, b = users[first], users[second]
            yield W_SIMILAR_COLORS(
                f"{first} ({_names(a)}) and {second} ({_names(b)}) are too alike to tell "
                f"apart: ΔE {difference:.1f}, at least {self.options.min_delta_e:g} is needed",
                path=picture.path(b[0]),
                objects=list(dict.fromkeys([*a, *b])),
                hint="give different concepts clearly different colors; if they are one "
                "concept, give them one color",
            )


def _colors(item: lir.PathItem | lir.TextItem | lir.MathItem) -> list[str]:
    if isinstance(item, lir.PathItem):
        return [paint.color for paint in (item.fill, item.stroke) if paint is not None]
    return [item.color]


def _names(owners: list[str]) -> str:
    shown = ", ".join(f"'{owner}'" for owner in owners[:3])
    return shown + (f" and {len(owners) - 3} more" if len(owners) > 3 else "")
