"""Where boxes go: the points of a box, beside a point or another box, and grids.

Plain arithmetic on boxes in units; place.py decides which boxes to use.

Beside: a box placed beside a point (or another box) in direction u sits
on the ray from the point (or the other box's center) along u, so that the
gap between the two, measured along u, is ``gap``. For ``right`` that is
the familiar "left edge ``gap`` right of the other's right edge, centered
vertically"; for any other angle it is the same rule, so a label can sit at
135 degrees as easily as up or left.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from irpipe.frontend.geometry.affine import XY, Box
from irpipe.schema.ir import Direction

DIRECTIONS: dict[str, XY] = {
    "up": (0.0, 1.0),
    "down": (0.0, -1.0),
    "left": (-1.0, 0.0),
    "right": (1.0, 0.0),
    "up_left": (-math.sqrt(0.5), math.sqrt(0.5)),
    "up_right": (math.sqrt(0.5), math.sqrt(0.5)),
    "down_left": (-math.sqrt(0.5), -math.sqrt(0.5)),
    "down_right": (math.sqrt(0.5), -math.sqrt(0.5)),
}


def anchor_parts(anchor: str) -> tuple[str, str]:
    """``"left_baseline"`` -> (``"left"``, ``"baseline"``); ``"center"`` -> both center."""
    if anchor == "center":
        return "center", "center"
    horizontal, _, vertical = anchor.partition("_")
    return horizontal, vertical


def box_point(box: Box, anchor: str, baseline: float | None = None) -> XY:
    """The ``anchor`` point of ``box``; a baseline anchor needs the box's ``baseline``."""
    x0, y0, x1, y1 = box
    horizontal, vertical = anchor_parts(anchor)
    x = {"left": x0, "center": (x0 + x1) / 2, "right": x1}[horizontal]
    if vertical == "baseline":
        if baseline is None:
            raise ValueError(f"'{anchor}' needs a baseline, and this box has none")
        return x, baseline
    return x, {"top": y1, "center": (y0 + y1) / 2, "bottom": y0}[vertical]


def box_at(at: XY, anchor: str, width: float, ascent: float, descent: float) -> tuple[Box, float]:
    """The box and baseline of a box whose ``anchor`` point sits at ``at``.

    The box reaches ``ascent`` above its baseline and ``descent`` below it.
    Vertically, ``center`` is the middle from descent to ascent.
    """
    horizontal, vertical = anchor_parts(anchor)
    x, y = at
    x0 = {"left": x, "center": x - width / 2, "right": x - width}[horizontal]
    baseline = {
        "top": y - ascent,
        "center": y - (ascent - descent) / 2,
        "baseline": y,
        "bottom": y + descent,
    }[vertical]
    return (x0, baseline - descent, x0 + width, baseline + ascent), baseline


def unit_vector(direction: Direction) -> XY:
    """A direction as a vector of length 1."""
    if isinstance(direction, str):
        return DIRECTIONS[direction]
    if isinstance(direction, tuple):
        norm = math.hypot(*direction)
        return (direction[0] / norm, direction[1] / norm)
    turn = math.radians(direction)
    return (math.cos(turn), math.sin(turn))


def reach(width: float, height: float, u: XY) -> float:
    """How far a box's edge is from its center, going along the unit vector ``u``."""
    limits = [half / abs(c) for half, c in ((width / 2, u[0]), (height / 2, u[1])) if c != 0]
    return min(limits) if limits else 0.0


def beside(target: Box, u: XY, gap: float, width: float, height: float) -> XY:
    """The center of a ``width`` x ``height`` box beside ``target``, ``gap`` away along ``u``.

    ``target`` may be a point, as a box with no size.
    """
    x0, y0, x1, y1 = target
    distance = reach(x1 - x0, y1 - y0, u) + gap + reach(width, height, u)
    return ((x0 + x1) / 2 + u[0] * distance, (y0 + y1) / 2 + u[1] * distance)


@dataclass(frozen=True)
class Grid:
    """Cells for a stack's children, with the grid's left-top corner at (0, 0)."""

    cells: tuple[Box, ...]
    baselines: tuple[float, ...]
    """Where each cell's row puts its baselines when the row lines up on them."""
    box: Box


def grid(
    sizes: Sequence[tuple[float, float, float]],
    columns: int,
    spacing: XY,
    *,
    on_baselines: bool,
) -> Grid:
    """Cells for children of the given (width, ascent, descent), filling rows of ``columns``.

    A column is as wide as its widest child and a row as tall as its tallest;
    ``on_baselines`` makes a row tall enough for its highest ascent and its
    deepest descent together, so that the children can share one baseline.
    """
    count = len(sizes)
    columns = min(columns, count)
    rows = math.ceil(count / columns)
    widths = [max(sizes[k][0] for k in range(c, count, columns)) for c in range(columns)]
    cells: list[Box] = []
    baselines: list[float] = []
    top = 0.0
    for r in range(rows):
        row = sizes[r * columns : (r + 1) * columns]
        up = max(ascent for _, ascent, _ in row)
        down = max(descent for _, _, descent in row)
        height = up + down if on_baselines else max(a + d for _, a, d in row)
        left = 0.0
        for c in range(len(row)):
            cells.append((left, top - height, left + widths[c], top))
            baselines.append(top - up)
            left += widths[c] + spacing[0]
        top -= height + spacing[1]
    width = sum(widths) + spacing[0] * (columns - 1)
    return Grid(tuple(cells), tuple(baselines), (0.0, top + spacing[1], width, 0.0))
