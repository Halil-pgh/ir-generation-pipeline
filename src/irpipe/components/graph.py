"""Component "graph": the curve y = f(x) of an expression, as one path.

    {"id": "f", "type": "graph", "function": "x**2/4", "x_range": [-2, 3], "in": "P"}

``function`` is an expression in ``x``, in the language the geometry's
expressions use; it may name the IR's ``values`` too. The curve is sampled
at ``samples`` evenly spaced x and drawn through every sample with cubic
pieces whose slopes come from the neighbouring samples, so it still meets
each x once. Where f is not defined (the root of a negative number, a
division by zero) the curve breaks; with ``y_range`` it is also cut where it
leaves that band.

It opens into a path with the graph's own id, so a region may lie under it,
a flood fill be bounded by it, and a point sit on it (``{"on": "f", "x": 2}``).
It takes a line's paint, a label and arrowheads.
"""

import math
from collections.abc import Callable, Mapping
from fractions import Fraction
from typing import Literal

from pydantic import Field

from irpipe.components.base import COMPONENTS, Component, ComponentError, Context, Expansion, make
from irpipe.expr import CONSTANTS, ExprError, Value, evaluate, names_used, parse
from irpipe.frontend.expressions import E_EXPR
from irpipe.schema.ir.common import Number
from irpipe.schema.ir.objects import Arrows, Path, Stroked

VARIABLE = "x"
CROSSING_STEPS = 40
"""Halvings that find where the curve leaves y_range (to 2**-40 of a sample step)."""

type Sample = tuple[float, float]


@COMPONENTS.register
class Graph(Component, Stroked, Arrows):
    type: Literal["graph"] = "graph"
    function: str = Field(min_length=1)
    """y as an expression of ``x``: ``"x**2/4 - 1"``, ``"sin(x)"``, ``"k*x"`` with a value k."""
    x_range: tuple[Number, Number]
    y_range: tuple[Number, Number] | None = None
    """The band the curve is kept in; it is cut where it leaves it."""
    samples: int = Field(default=200, ge=2, le=2000)

    def expand(self, context: Context) -> Expansion:
        x0, x1 = self.x_range
        if not x0 < x1:
            raise ComponentError(
                f"x_range runs from {x0:g} to {x1:g}",
                field="x_range",
                hint="give the smaller end first",
            )
        band = self.y_range
        if band is not None and not band[0] < band[1]:
            raise ComponentError(
                f"y_range runs from {band[0]:g} to {band[1]:g}",
                field="y_range",
                hint="give the smaller end first",
            )
        self._check_function(context.values)
        step = (x1 - x0) / (self.samples - 1)
        points = [
            (x, self._at(x, context.values)) for x in (x0 + k * step for k in range(self.samples))
        ]
        runs = _runs(points, band, lambda x: self._at(x, context.values))
        if not runs:
            raise ComponentError(
                f"y = {self.function} is not defined anywhere on x from {x0:g} to {x1:g}"
                + (f" within y from {band[0]:g} to {band[1]:g}" if band else ""),
                field="function",
            )
        root = make(
            Path,
            self.id,
            context.values,
            subpaths=[_subpath(run) for run in runs],
            **{"in": self.space},
            **self.shared(),
            tags=self.made_tags(),
            color=self.color,
            stroke_width=self.stroke_width,
            dash=self.dash,
            label=self.label,
            arrows=self.arrows,
            arrow_size=self.arrow_size,
        )
        return Expansion(root)

    def _check_function(self, values: Mapping[str, Value]) -> None:
        try:
            node = parse(self.function)
        except ExprError as error:
            raise ComponentError(
                str(error), field="function", hint=error.hint, code=E_EXPR
            ) from None
        known = {VARIABLE, *values, *CONSTANTS}
        for name in sorted(names_used(node) - known):
            raise ComponentError(
                f"unknown name '{name}'",
                field="function",
                hint=f"the variable is '{VARIABLE}'; other names come from values",
                code=E_EXPR,
            )

    def _at(self, x: float, values: Mapping[str, Value]) -> float | None:
        """f(x), or None where f is not defined there.

        x goes in as an exact fraction, so a polynomial is computed exactly:
        the evaluator refuses a whole power of a negative float (S8 in
        docs/PLAN.md), but not of a fraction.
        """
        try:
            y = float(evaluate(self.function, {**values, VARIABLE: Fraction(x)}))
        except (ExprError, OverflowError, ZeroDivisionError):
            return None
        return y if math.isfinite(y) else None


def _runs(
    points: list[tuple[float, float | None]],
    band: tuple[float, float] | None,
    f: Callable[[float], float | None],
) -> list[list[Sample]]:
    """The samples in unbroken runs of two or more, cut at the band's edges."""
    runs: list[list[Sample]] = []
    run: list[Sample] = []
    previous: tuple[float, float | None] | None = None
    for x, y in points:
        inside = y is not None and (band is None or band[0] <= y <= band[1])
        if inside:
            assert y is not None
            if not run and previous is not None and previous[1] is not None:
                run.append(_crossing(previous, (x, y), band, f))  # back into the band
            run.append((x, y))
        else:
            if run and y is not None and band is not None:
                run.append(_crossing(run[-1], (x, y), band, f))  # leaving the band
            if len(run) >= 2:
                runs.append(run)
            run = []
        previous = (x, y)
    if len(run) >= 2:
        runs.append(run)
    return runs


def _crossing(
    a: tuple[float, float | None],
    b: tuple[float, float | None],
    band: tuple[float, float] | None,
    f: Callable[[float], float | None],
) -> Sample:
    """Where the curve crosses the band's edge between samples a and b, found by halving
    (on the straight line between them where f is not defined in between)."""
    assert band is not None and a[1] is not None and b[1] is not None
    (xa, ya), (xb, yb) = (a[0], a[1]), (b[0], b[1])
    edge = band[1] if max(ya, yb) > band[1] else band[0]
    below = ya < edge
    for _ in range(CROSSING_STEPS):
        middle = (xa + xb) / 2
        y = f(middle)
        if y is None:
            t = (edge - ya) / (yb - ya)
            return (xa + t * (xb - xa), edge)
        if (y < edge) == below:
            xa, ya = middle, y
        else:
            xb, yb = middle, y
    return ((xa + xb) / 2, edge)


def _subpath(run: list[Sample]) -> dict[str, object]:
    """Cubic pieces through every sample, with slopes from the neighbours (a cubic Hermite
    curve in x: each piece's handles stay within its own x, so the curve meets each x once)."""
    n = len(run)
    slopes = []
    for k in range(n):
        left, right = run[max(k - 1, 0)], run[min(k + 1, n - 1)]
        slopes.append((right[1] - left[1]) / (right[0] - left[0]))
    segments = []
    for k in range(n - 1):
        (xa, ya), (xb, yb) = run[k], run[k + 1]
        third = (xb - xa) / 3
        handles = [[xa + third, ya + slopes[k] * third], [xb - third, yb - slopes[k + 1] * third]]
        segments.append({"cubic": [*handles, [xb, yb]]})
    return {"start": list(run[0]), "segments": segments}
