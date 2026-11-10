"""Component "angle": the mark of an angle between two arms, with a label.

    {"id": "theta", "type": "angle", "vertex": [0, 0], "arms": [[3, 0], [2, 3]],
     "label": {"tex": "\\\\theta"}}

``arms`` are a point on each arm; the angle runs counterclockwise from the
first arm to the second, so swapping them marks the other side. It is an
arc of ``radius`` (0.5 frame units when left out) around the vertex, or a
square corner when the angle is a right one (``right`` says so either way).
Its label sits at the mark's ``mid`` point, on the bisector, beside it
outward, unless it says otherwise.

It opens into one arc (or, for a right angle, a polyline) with the angle's
id; the label is that shape's label.
"""

import math
from typing import Literal

from irpipe.components.base import COMPONENTS, Component, ComponentError, Context, Expansion, make
from irpipe.schema.ir.common import XY, PositiveNumber
from irpipe.schema.ir.objects import Arc, Polyline, Stroked

RADIUS = 0.5
"""The arc's radius when ``radius`` is left out, in frame units."""
SQUARE = 0.7
"""A right angle's square side, as a share of the radius."""
RIGHT_TOLERANCE = 1e-3
"""Degrees within which an angle counts as a right one."""


@COMPONENTS.register
class Angle(Component, Stroked):
    type: Literal["angle"] = "angle"
    vertex: XY
    arms: tuple[XY, XY]
    radius: PositiveNumber | None = None
    right: bool | None = None

    def expand(self, context: Context) -> Expansion:
        (vx, vy) = self.vertex
        turns = []
        for k, (x, y) in enumerate(self.arms):
            if (x, y) == (vx, vy):
                raise ComponentError("an arm's point is the vertex itself", field=f"arms[{k}]")
            turns.append(math.degrees(math.atan2(y - vy, x - vx)))
        start, sweep = turns[0], (turns[1] - turns[0]) % 360
        if sweep == 0:
            raise ComponentError("both arms point the same way", field="arms")
        radius = self.radius if self.radius is not None else context.length(RADIUS, self.space)
        right = self.right if self.right is not None else abs(sweep - 90) < RIGHT_TOLERANCE
        bisector = math.radians(start + sweep / 2)
        label = None
        if self.label is not None:
            placed = {"at": "mid", "dir": (math.cos(bisector), math.sin(bisector))}
            label = self.label.model_copy(
                update={k: v for k, v in placed.items() if k not in self.label.model_fields_set}
            )
        paint = {
            **self.shared(),
            "in": self.space,
            "tags": self.made_tags(),
            "color": self.color,
            "stroke_width": self.stroke_width,
            "dash": self.dash,
            "label": label,
        }
        if right:
            side = SQUARE * radius
            a, b = math.radians(turns[0]), math.radians(turns[1])
            first = [vx + side * math.cos(a), vy + side * math.sin(a)]
            last = [vx + side * math.cos(b), vy + side * math.sin(b)]
            corner = [first[0] + last[0] - vx, first[1] + last[1] - vy]
            root = make(Polyline, self.id, context.values, points=[first, corner, last], **paint)
        else:
            arc = {"center": [vx, vy], "radius": radius, "start_angle": start}
            root = make(Arc, self.id, context.values, **arc, end_angle=start + sweep, **paint)
        return Expansion(root)
