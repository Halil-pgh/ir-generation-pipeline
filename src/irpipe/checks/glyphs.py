"""Check "glyphs": every character of a text is in its font (analysis §2.5).

A character the font has no glyph for is drawn as an empty box. The font is
the one fontconfig picks for the text's family, as Pango does; without
fontconfig nothing can be known and nothing is reported. Formulas are set
by TeX and are not checked here.
"""

from collections.abc import Iterable

from irpipe.checks.base import CHECKS, Check
from irpipe.checks.picture import Picture
from irpipe.core import ISSUE_CODES, Issue, IssueCode, Origin
from irpipe.metrics import fonts
from irpipe.schema import lir

W_MISSING_GLYPH = ISSUE_CODES.register(
    IssueCode("W-MISSING-GLYPH", Origin.IR, "a text uses a character its font has no glyph for")
)


@CHECKS.register
class Glyphs(Check):
    name = "glyphs"
    codes = (W_MISSING_GLYPH,)

    def check(self, picture: Picture) -> Iterable[Issue]:
        for text in picture.texts:
            item = text.item
            if not isinstance(item, lir.TextItem):
                continue
            absent = fonts.missing(item.font, item.text)
            if absent:
                shown = ", ".join(f"{char} (U+{ord(char):04X})" for char in absent)
                yield W_MISSING_GLYPH(
                    f"'{text.owner}' uses {shown}, which font '{item.font}' has no glyph "
                    "for; it is drawn as an empty box",
                    path=picture.path(text.owner),
                    objects=[text.owner],
                    hint="write the symbol in a formula (math), or choose a font that has it",
                )
