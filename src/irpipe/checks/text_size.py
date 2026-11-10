"""Check "text_size": no text or formula is too small to read (analysis §2.5).

Sizes are reference px (short side 1080), so one limit holds for every
aspect ratio and resolution. A formula counts by its size, though its
sub- and superscripts are smaller still.
"""

from collections.abc import Iterable

from pydantic import PositiveFloat

from irpipe.checks.base import CHECKS, Check
from irpipe.checks.picture import Picture
from irpipe.core import ISSUE_CODES, Issue, IssueCode, Origin
from irpipe.schema import lir
from irpipe.schema.base import StrictModel

W_SMALL_TEXT = ISSUE_CODES.register(
    IssueCode("W-SMALL-TEXT", Origin.IR, "a text or formula is too small to read", allowable=True)
)


class TextSizeOptions(StrictModel):
    min_size: PositiveFloat = 28
    """Reference px; a caption is usually 34."""


@CHECKS.register
class TextSize(Check):
    name = "text_size"
    codes = (W_SMALL_TEXT,)
    options_model = TextSizeOptions

    def check(self, picture: Picture) -> Iterable[Issue]:
        for text in picture.texts:
            item = text.item
            assert isinstance(item, lir.TextItem | lir.MathItem)
            if item.size < self.options.min_size:
                yield W_SMALL_TEXT(
                    f"'{text.owner}' is set at {item.size:g} px; the smallest size that "
                    f"reads well is {self.options.min_size:g} px (reference px, short side 1080)",
                    path=picture.path(text.owner),
                    objects=[text.owner],
                    hint="use a text role from the header (label, caption) or a larger size",
                )
