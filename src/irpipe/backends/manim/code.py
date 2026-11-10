"""Small pieces of Python source: numbers, points, string literals and calls.

scene.py is read by people, so numbers are short (``2.4``, not
``2.4000000000000004``), TeX is a raw string, and a call too long for one
line is broken the way a person would break it:

    shape = _path(
        [(2.2, -1), (1.9167, -0.8867), (1.9167, -1.1133), "close"],
    )
"""

from collections.abc import Sequence
from dataclasses import dataclass

from irpipe.schema.lir import Point

WIDTH = 99
"""The longest line scene.py writes."""

BODY = 4
"""Columns a function body is indented by."""


def num(value: float, digits: int = 4) -> str:
    """A short, stable number: at most ``digits`` decimals, no trailing zeros."""
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return "0" if text in {"-0", ""} else text


def xy(point: Point) -> str:
    return f"({num(point[0])}, {num(point[1])})"


def xyz(point: Point) -> str:
    """A point as Manim takes it: three coordinates."""
    return f"[{num(point[0])}, {num(point[1])}, 0]"


def degrees(angle: float) -> str:
    return f"{num(angle)} * DEGREES"


def text_literal(value: str) -> str:
    """A Python string literal, in double quotes when it can be."""
    if '"' in value or "\\" in value or not value.isprintable():
        return repr(value)
    return f'"{value}"'


def tex_literal(value: str) -> str:
    """TeX as a raw string, so its backslashes read as written."""
    if '"' in value or value.endswith("\\") or not value.isprintable():
        return repr(value)
    return f'r"{value}"'


def split_literal(literal: str, room: int) -> str:
    """A long string literal as pieces on lines of their own, which Python joins back.

    Only a plain ``"..."`` or ``r"..."`` is split, and only after a space, so
    every piece reads exactly as the whole did; anything else stays as it is.
    """
    prefix = "r" if literal.startswith('r"') else ""
    value = literal[len(prefix) + 1 : -1]
    if len(literal) <= room or not literal.endswith('"') or '"' in value or "\\\n" in value:
        return literal
    if literal[len(prefix)] != '"':
        return literal
    pieces, piece = [], ""
    for word in value.split(" "):
        candidate = f"{piece} {word}" if piece else word
        if piece and len(candidate) + len(prefix) + 3 > room:
            pieces.append(piece + " ")
            piece = word
        else:
            piece = candidate
    pieces.append(piece)
    return "\n".join(f'{prefix}"{p}"' for p in pieces)


def pack(tokens: Sequence[str], column: int) -> list[str]:
    """Tokens joined by ", " into lines that start at ``column``; every line but the last
    ends with a comma."""
    lines, line = [], ""
    for token in tokens:
        candidate = f"{line}, {token}" if line else token
        if line and column + len(candidate) + 2 > WIDTH:
            lines.append(line + ",")
            line = token
        else:
            line = candidate
    lines.append(line)
    return lines


@dataclass(frozen=True)
class Call:
    """``func(args...)suffix``, kept in parts so a long one can be broken over lines.

    An argument may itself span lines (a subpath); its later lines are
    indented relative to its first.
    """

    func: str
    args: Sequence[str]
    suffix: str = ""

    def assign(self, name: str) -> list[str]:
        """``name = func(...)`` as lines of a function body (without the body's indent)."""
        line = f"{name} = {self.func}({', '.join(self.args)}){self.suffix}"
        if BODY + len(line) <= WIDTH and "\n" not in line:
            return [line]
        inner = BODY + 4
        if any("\n" in arg or inner + len(arg) + 1 > WIDTH for arg in self.args):
            args = [split_literal(arg, room=WIDTH - inner - 1) for arg in self.args]
            rows = [row for arg in args for row in f"{arg},".split("\n")]
        else:
            rows = pack(self.args, column=inner)
            rows[-1] += ","
        return [f"{name} = {self.func}(", *(f"    {row}" for row in rows), f"){self.suffix}"]
