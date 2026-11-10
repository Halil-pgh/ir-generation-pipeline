"""Check "safe_area": everything stays inside the safe area.

The safe area is the frame without its margins, the platform's interface
(captions, buttons) and the subtitle band (header ``frame.safe``, analysis
§2.1). Whatever lies outside it may be covered or cut on the platform.
"""

from collections.abc import Iterable

from irpipe.checks.base import CHECKS, Check
from irpipe.checks.frame import sides
from irpipe.checks.picture import Picture, beyond, reach_of
from irpipe.core import ISSUE_CODES, Issue, IssueCode, Origin

W_UNSAFE = ISSUE_CODES.register(
    IssueCode("W-UNSAFE", Origin.IR, "an object reaches outside the safe area", allowable=True)
)


@CHECKS.register
class SafeArea(Check):
    name = "safe_area"
    codes = (W_UNSAFE,)

    def check(self, picture: Picture) -> Iterable[Issue]:
        for owner, drawn in picture.by_owner().items():
            past = beyond(reach_of(drawn), picture.safe)
            if past:
                yield W_UNSAFE(
                    f"'{owner}' reaches {sides(past, 'the safe area')}",
                    path=picture.path(owner),
                    objects=[owner],
                    hint="the safe area keeps clear of margins and the platform's interface; "
                    'move it in (references such as "safe.left_top" help)',
                )
