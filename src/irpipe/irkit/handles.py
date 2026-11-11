"""Handles: what the builders hand back, so a script refers to objects by variable, not by
retyping their ids.

    a = pic.line("a", start=(0, 0), end=(2, 3), arrows=["end"], label=label(tex="a"))
    a.tip                  "a.tip": an anchor (analysis §2.3); a name a line lacks is an
                           AttributeError, with the names it has
    f.at(x=2)              {"on": "f", "x": 2}: a point on f's outline
    a.label.center         "a.label.center": the label is an object of its own
    ax.part("x_axis")      the part "ax.x_axis" of a component
    a.id, str(a)           "a"

Wherever the IR wants an id (children, next_to, bounded_by, focus, a
region's operand, a space in ``space=``), the handle can stand in for it.
``pic.frame`` and ``pic.safe`` are handles of the picture's own boxes;
spaces and zones have handles too.
"""

import difflib
from dataclasses import dataclass
from typing import Any

from irpipe.frontend.anchors import BASELINE_ANCHORS, BOX_ANCHORS


@dataclass(frozen=True)
class Handle:
    """An object, a part, a space, a zone or one of the picture's boxes, by id."""

    id: str
    kind: str
    """The object's type (``"line"``), or ``"space"``, ``"zone"``, ``"frame"``, ``"part"``."""
    anchors: tuple[str, ...] = ()
    labelled: bool = False

    def __getattr__(self, name: str) -> str:
        if name.startswith("_") or name in ("id", "kind", "anchors", "labelled"):
            raise AttributeError(name)
        if name in self.anchors:
            return f"{self.id}.{name}"
        if name == "label":  # the property found no label; Python then asks here
            raise AttributeError(f"'{self.id}' was given no label")
        if not self.anchors:
            raise AttributeError(f"a {self.kind} has no anchors, so '{self.id}.{name}' is no point")
        close = difflib.get_close_matches(name, self.anchors, n=1)
        hint = f"did you mean '{close[0]}'?" if close else f"it has: {', '.join(self.anchors)}"
        raise AttributeError(f"'{self.id}' ({self.kind}) has no anchor '{name}'; {hint}")

    def __str__(self) -> str:
        return self.id

    def at(self, *, t: Any = None, x: Any = None) -> dict[str, Any]:
        """A point on the outline: ``t`` of the way along it (0 to 1, by length), or where it
        first reaches ``x`` in its own coordinates."""
        if (t is None) == (x is None):
            raise TypeError("give t or x, one of them")
        return {"on": self.id, "t": t} if x is None else {"on": self.id, "x": x}

    @property
    def label(self) -> "Handle":
        """The object's label, drawn as the object ``<id>.label``."""
        if not self.labelled:
            raise AttributeError(f"'{self.id}' was given no label")
        return Handle(f"{self.id}.label", "label", BOX_ANCHORS + BASELINE_ANCHORS)

    def part(self, name: str) -> "Handle":
        """A part a component opens into (``ax.part("x_axis")`` is ``ax.x_axis``)."""
        return Handle(f"{self.id}.{name}", "part", self.anchors)
