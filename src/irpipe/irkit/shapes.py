"""The small pieces a field takes: labels, mixed colors, region expressions and path pieces.

    label(tex="a", at="tip", dir="up_right")       a shape's label
    mix("a", "b")                                  an extra color mixed from two
    difference(square, disc)                       {"difference": ["square", "disc"]}
    union(a, b), intersection(a, b), xor(a, b)
    half_plane(p, q), under(f, x=(0, 2)), between(f, g, x=(0, 2))
    through(points, closed=False)                  a subpath of straight pieces
    smooth(points, closed=False)                   a subpath of cubic pieces through the points

They return plain dicts (with handles and exact numbers in them); the
builder writes them out with the rest of the object. ``through`` and
``smooth`` are the shortcuts the IR itself leaves out (decision K36: a path
is a start and its segments, nothing else): a path through many points is
one ``through`` call in the script, not a second way of writing a path.
``smooth`` passes through every point with Catmull-Rom tangents, the
neighbours' difference over 6, exact when the points are.
"""

from collections.abc import Sequence
from fractions import Fraction
from typing import Any

from irpipe.irkit.errors import at_the_call
from irpipe.irkit.fields import checked
from irpipe.schema.ir import Label

type Point = Any
"""Two numbers, an anchor (``a.tip``) or a point on an outline (``f.at(x=2)``)."""


@at_the_call
def label(text: str | None = None, *, tex: str | None = None, **fields: Any) -> dict[str, Any]:
    """A label: ``text`` or ``tex``, and where it sits (``at``, ``dir``, ``gap``), its ``size``,
    ``color``, ``weight``, ``italic``."""
    return checked(Label, "a label", {"text": text, "tex": tex, **fields})


def mix(first: Any, second: Any) -> dict[str, Any]:
    """An extra color mixed from two others (``pic.color("ab", mix("a", "b"))``)."""
    return {"mix": [first, second]}


def union(*areas: Any) -> dict[str, Any]:
    return {"union": list(areas)}


def intersection(*areas: Any) -> dict[str, Any]:
    return {"intersection": list(areas)}


def difference(first: Any, *others: Any) -> dict[str, Any]:
    """``first`` without every one of ``others``."""
    return {"difference": [first, *others]}


def xor(first: Any, second: Any) -> dict[str, Any]:
    return {"xor": [first, second]}


def half_plane(p: Point, q: Point) -> dict[str, Any]:
    """Everything left of the line from ``p`` to ``q``."""
    return {"half_plane": [p, q]}


def under(graph: Any, *, x: tuple[Any, Any]) -> dict[str, Any]:
    """Between ``graph`` and y = 0 of its coordinates, for x from ``x[0]`` to ``x[1]``."""
    return {"under": graph, "x": list(x)}


def between(first: Any, second: Any, *, x: tuple[Any, Any]) -> dict[str, Any]:
    """Between two graphs, for x from ``x[0]`` to ``x[1]``."""
    return {"between": [first, second], "x": list(x)}


def through(points: Sequence[Point], *, closed: bool = False) -> dict[str, Any]:
    """A subpath from the first point through the others in straight pieces."""
    if len(points) < 2:
        raise ValueError(f"a subpath through points needs two of them; got {len(points)}")
    return {
        "start": points[0],
        "segments": [{"line": point} for point in points[1:]],
        "closed": closed,
    }


def smooth(points: Sequence[Sequence[Any]], *, closed: bool = False) -> dict[str, Any]:
    """A subpath through numeric points in cubic pieces that meet without a corner.

    Each piece from p1 to p2 has handles p1 + (p2 - p0) / 6 and p2 - (p3 - p1) / 6,
    where p0 and p3 are the neighbours (an open end is its own neighbour).
    """
    pts = [(_exact(x), _exact(y)) for x, y in points]
    if len(pts) < 2:
        raise ValueError(f"a smooth subpath needs two points; got {len(pts)}")
    count = len(pts)

    def at(k: int) -> tuple[Any, Any]:
        return pts[k % count] if closed else pts[min(max(k, 0), count - 1)]

    segments = []
    for k in range(count if closed else count - 1):
        p0, p1, p2, p3 = at(k - 1), at(k), at(k + 1), at(k + 2)
        first = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        second = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        segments.append({"cubic": [first, second, p2]})
    return {"start": pts[0], "segments": segments, "closed": closed}


def _exact(value: Any) -> Any:
    """Whole numbers become Fractions, so that dividing them stays exact."""
    return Fraction(value) if isinstance(value, int) and not isinstance(value, bool) else value
