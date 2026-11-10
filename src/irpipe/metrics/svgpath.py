"""SVG path data -> subpaths of straight, quadratic and cubic segments.

Glyph outlines arrive as SVG path data (from dvisvgm). This reads the
commands fonts use, absolute and relative: M L H V C S Q T Z. Arcs (A) never
occur in glyph outlines and are refused. Coordinates are returned as written
(SVG's y points down); the caller places and flips them.
"""

import re
from dataclasses import dataclass, field

_TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtZzAa]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")

type Point = tuple[float, float]
type Segment = tuple[str, tuple[Point, ...]]
"""``("line", (end,))``, ``("quad", (control, end))`` or ``("cubic", (c1, c2, end))``."""


@dataclass
class Subpath:
    start: Point
    segments: list[Segment] = field(default_factory=list)
    closed: bool = False


class PathDataError(ValueError):
    """SVG path data this reader does not understand."""


def parse_path(data: str) -> list[Subpath]:
    tokens = _TOKEN.findall(data)
    subpaths: list[Subpath] = []
    current: Subpath | None = None
    pen: Point = (0.0, 0.0)
    last_cubic: Point | None = None  # S mirrors the previous cubic's second control
    last_quad: Point | None = None  # T mirrors the previous quadratic's control
    command = ""
    relative = False
    i = 0

    def at(x: float, y: float) -> Point:
        """A point of the current command, made absolute."""
        return (pen[0] + x, pen[1] + y) if relative else (x, y)

    def numbers(count: int) -> list[float]:
        nonlocal i
        values = tokens[i : i + count]
        if len(values) < count or any(v.isalpha() for v in values):
            raise PathDataError(f"command {command} needs {count} numbers")
        i += count
        return [float(v) for v in values]

    while i < len(tokens):
        if tokens[i].isalpha():
            command = tokens[i]
            i += 1
        elif not command:
            raise PathDataError("path data must start with a command")
        relative = command.islower()
        kind = command.upper()

        if kind == "Z":
            if current is not None:
                current.closed = True
                pen = current.start
            current, last_cubic, last_quad = None, None, None
            command = ""  # Z takes no numbers; the next token must be a command
            continue
        if kind == "A":
            raise PathDataError("arcs (A) are not supported in glyph outlines")
        if kind == "M":
            pen = at(*numbers(2))
            current = Subpath(pen)
            subpaths.append(current)
            command = "l" if relative else "L"  # further pairs are line-tos
            last_cubic = last_quad = None
            continue
        if current is None:  # drawing right after Z starts from the closed subpath's start
            current = Subpath(pen)
            subpaths.append(current)
        if kind in "LHV":
            if kind == "L":
                end = at(*numbers(2))
            elif kind == "H":
                (x,) = numbers(1)
                end = (pen[0] + x if relative else x, pen[1])
            else:
                (y,) = numbers(1)
                end = (pen[0], pen[1] + y if relative else y)
            current.segments.append(("line", (end,)))
            pen, last_cubic, last_quad = end, None, None
        elif kind in "CS":
            # In S, the first control mirrors the previous cubic's second one.
            c1 = at(*numbers(2)) if kind == "C" else _mirror(last_cubic, pen)
            c2, end = at(*numbers(2)), at(*numbers(2))
            current.segments.append(("cubic", (c1, c2, end)))
            pen, last_cubic, last_quad = end, c2, None
        elif kind in "QT":
            c = at(*numbers(2)) if kind == "Q" else _mirror(last_quad, pen)
            end = at(*numbers(2))
            current.segments.append(("quad", (c, end)))
            pen, last_cubic, last_quad = end, None, c
    return [s for s in subpaths if s.segments]


def _mirror(control: Point | None, about: Point) -> Point:
    """``control`` reflected through ``about``; with no previous control, ``about`` itself."""
    if control is None:
        return about
    return (2 * about[0] - control[0], 2 * about[1] - control[1])
