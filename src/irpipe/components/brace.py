"""Component "brace": a curly brace along a segment, with a label at its tip.

    {"id": "br", "type": "brace", "start": [1, -0.4], "end": [3, -0.4],
     "label": {"tex": "\\\\Delta x"}}

The brace runs from ``start`` to ``end`` and bulges to the right of that way
(below a segment drawn left to right); ``"side": "left"`` turns it over.
``depth`` is how far its tip stands out, 0.25 frame units when left out.
Its label sits beyond the tip: at the brace's ``mid`` point, which is the
tip, beside it in the way the brace points, unless it says otherwise.

It opens into one path with the brace's id; the label is that path's label.
"""

import math
from typing import Literal

from irpipe.components.base import COMPONENTS, Component, ComponentError, Context, Expansion, make
from irpipe.schema.ir.common import XY, PositiveNumber
from irpipe.schema.ir.objects import Path, Stroked

DEPTH = 0.25
"""How far the tip stands out when ``depth`` is left out, in frame units."""
ROUND = 0.55
"""How far a curl's handles reach, as a share of its size (a quarter circle's is 0.552)."""


@COMPONENTS.register
class Brace(Component, Stroked):
    type: Literal["brace"] = "brace"
    start: XY
    end: XY
    side: Literal["right", "left"] = "right"
    depth: PositiveNumber | None = None

    def expand(self, context: Context) -> Expansion:
        (x0, y0), (x1, y1) = self.start, self.end
        length = math.hypot(x1 - x0, y1 - y0)
        if length == 0:
            raise ComponentError("start and end are the same point", field="end")
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        nx, ny = (uy, -ux) if self.side == "right" else (-uy, ux)
        depth = self.depth if self.depth is not None else context.length(DEPTH, self.space)

        def at(a: float, b: float) -> list[float]:
            """The point ``a`` along the segment and ``b`` out of it."""
            return [x0 + a * ux + b * nx, y0 + a * uy + b * ny]

        h, half = depth / 2, length / 2
        r = min(h, length / 4)  # the curls' size
        inset = 1 - ROUND
        pieces = [  # (handle, handle, end), in (along, out)
            ((0, ROUND * h), (inset * r, h), (r, h)),
            None,
            ((half - inset * r, h), (half, h + ROUND * h), (half, depth)),
            ((half, h + ROUND * h), (half + inset * r, h), (half + r, h)),
            None,
            ((length - inset * r, h), (length, ROUND * h), (length, 0)),
        ]
        flats = iter([(half - r, h), (length - r, h)])
        segments: list[dict[str, object]] = []
        for piece in pieces:
            if piece is None:
                segments.append({"line": at(*next(flats))})
            else:
                segments.append({"cubic": [at(*p) for p in piece]})
        label = None
        if self.label is not None:
            placed = {"at": "mid", "dir": (nx, ny)}  # a validated form: model_copy does not check
            label = self.label.model_copy(
                update={k: v for k, v in placed.items() if k not in self.label.model_fields_set}
            )
        root = make(
            Path,
            self.id,
            context.values,
            subpaths=[{"start": at(0, 0), "segments": segments}],
            **{"in": self.space},
            **self.shared(),
            tags=self.made_tags(),
            color=self.color,
            stroke_width=self.stroke_width,
            dash=self.dash,
            label=label,
        )
        return Expansion(root)
