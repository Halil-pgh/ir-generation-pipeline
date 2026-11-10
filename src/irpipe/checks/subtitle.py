"""Check "subtitle": nothing is drawn in the subtitle band (analysis §2.2).

With the subtitle mode ``reserve`` or ``burn_in`` the header keeps a band
for subtitles; drawing into it is an error, since subtitles will cover it.
(Subtitles the front-end draws there itself, in ``burn_in`` mode, will not
count once they exist.)
"""

from collections.abc import Iterable
from typing import Final

from shapely.geometry import box

from irpipe.checks.base import CHECKS, Check
from irpipe.checks.picture import Picture
from irpipe.core import ISSUE_CODES, Issue, IssueCode, Origin

E_SUBTITLE = ISSUE_CODES.register(
    IssueCode("E-SUBTITLE", Origin.IR, "an object is drawn in the subtitle band")
)

TOUCH: Final = 1e-6
"""An area or length below this is a touch on the band's edge, not a way in."""


@CHECKS.register
class Subtitle(Check):
    name = "subtitle"
    codes = (E_SUBTITLE,)

    def check(self, picture: Picture) -> Iterable[Issue]:
        if picture.band is None:
            return
        band = box(*picture.band)
        _, y0, _, y1 = picture.band
        for owner, drawn in picture.by_owner().items():
            inside = any(d.ink.intersection(band).area > TOUCH for d in drawn)
            if inside:
                yield E_SUBTITLE(
                    f"'{owner}' is drawn in the subtitle band (y from {y0:g} to {y1:g})",
                    path=picture.path(owner),
                    objects=[owner],
                    hint="keep everything above the band; the safe area already leaves it out",
                )
