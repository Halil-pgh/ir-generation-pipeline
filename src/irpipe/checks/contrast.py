"""Check "contrast": every text stands out from what is behind it (analysis §2.4).

The color behind a text is the one actually there: the background with
every fill drawn before the text laid over it at its opacity. It is looked
at on a 3 x 3 grid of points inside the text's box, and the worst point
counts. A text's own opacity mixes it with what is behind. The ratio is
WCAG's; large text needs less.
"""

from collections.abc import Iterable

from pydantic import PositiveFloat

from irpipe import colormath
from irpipe.checks.base import CHECKS, Check
from irpipe.checks.picture import Picture
from irpipe.core import ISSUE_CODES, Issue, IssueCode, Origin
from irpipe.schema import lir
from irpipe.schema.base import StrictModel

W_LOW_CONTRAST = ISSUE_CODES.register(
    IssueCode(
        "W-LOW-CONTRAST",
        Origin.IR,
        "a text does not stand out enough from what is behind it",
        allowable=True,
    )
)


class ContrastOptions(StrictModel):
    min_ratio: PositiveFloat = 4.5
    """WCAG AA for text."""
    large_ratio: PositiveFloat = 3.0
    """WCAG AA for large text."""
    large_size: PositiveFloat = 48
    """Reference px from which a text counts as large."""


@CHECKS.register
class Contrast(Check):
    name = "contrast"
    codes = (W_LOW_CONTRAST,)
    options_model = ContrastOptions

    def check(self, picture: Picture) -> Iterable[Issue]:
        for text in picture.texts:
            item = text.item
            assert isinstance(item, lir.TextItem | lir.MathItem)
            ink = colormath.rgb(item.color)
            x0, y0, x1, y1 = text.reach
            worst: tuple[float, colormath.RGB, colormath.RGB] | None = None
            for fx in (0.25, 0.5, 0.75):
                for fy in (0.25, 0.5, 0.75):
                    behind = picture.color_at(x0 + fx * (x1 - x0), y0 + fy * (y1 - y0), text.order)
                    seen = colormath.blend(ink, behind, item.opacity)
                    ratio = colormath.contrast(seen, behind)
                    if worst is None or ratio < worst[0]:
                        worst = (ratio, seen, behind)
            assert worst is not None
            ratio, seen, behind = worst
            large = item.size >= self.options.large_size
            needed = self.options.large_ratio if large else self.options.min_ratio
            if ratio < needed:
                yield W_LOW_CONTRAST(
                    f"'{text.owner}' has contrast {ratio:.1f}:1 against what is behind it "
                    f"({colormath.hex_of(seen)} on {colormath.hex_of(behind)}); "
                    f"it needs {needed:g}:1",
                    path=picture.path(text.owner),
                    objects=[text.owner],
                    hint="choose a lighter or darker color, or put the text where the "
                    "background is calmer",
                )
