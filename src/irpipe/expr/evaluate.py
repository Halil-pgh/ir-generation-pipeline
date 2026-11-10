"""Computing an expression, exactly where it can be.

Numbers are read as fractions, so ``+ - * /`` and whole powers stay exact:
``"0.1 + 0.2"`` is exactly 3/10 and ``"44/17 * 17"`` exactly 44. A square
root of a perfect square stays exact too. Everything else (``pi``, ``sin``,
other roots) is a float from then on. The result is always a finite real.

Angles in sin, cos, tan and their inverses are radians, as in sympy; the
IR's angle fields are degrees, so write ``180*atan2(3, 2)/pi`` there.
"""

import difflib
import math
from collections.abc import Callable, Mapping
from fractions import Fraction

from irpipe.expr.errors import ExprError
from irpipe.expr.syntax import Binary, Call, Name, Node, Number, Unary, parse

type Value = Fraction | float

CONSTANTS: dict[str, float] = {"pi": math.pi, "E": math.e}


def _sqrt(x: Value) -> Value:
    if x < 0:
        raise ExprError("square root of a negative number")
    if isinstance(x, Fraction):
        top, bottom = math.isqrt(x.numerator), math.isqrt(x.denominator)
        if top * top == x.numerator and bottom * bottom == x.denominator:
            return Fraction(top, bottom)
    return math.sqrt(float(x))


def _log(x: Value, base: Value | None = None) -> Value:
    if x <= 0 or (base is not None and (base <= 0 or base == 1)):
        raise ExprError("log needs a positive number (and a positive base other than 1)")
    return math.log(x) if base is None else math.log(x) / math.log(base)


def _inverse(name: str, f: Callable[[float], float]) -> Callable[[Value], float]:
    def checked(x: Value) -> float:
        if not -1 <= x <= 1:
            raise ExprError(f"{name} needs a number between -1 and 1")
        return f(float(x))

    return checked


FUNCTIONS: dict[str, tuple[Callable[..., Value], tuple[int, ...]]] = {
    "sqrt": (_sqrt, (1,)),
    "sin": (math.sin, (1,)),
    "cos": (math.cos, (1,)),
    "tan": (math.tan, (1,)),
    "asin": (_inverse("asin", math.asin), (1,)),
    "acos": (_inverse("acos", math.acos), (1,)),
    "atan": (math.atan, (1,)),
    "atan2": (math.atan2, (2,)),
    "exp": (math.exp, (1,)),
    "log": (_log, (1, 2)),
    "Abs": (abs, (1,)),
    "Min": (min, (2, 3, 4, 5, 6, 7, 8)),
    "Max": (max, (2, 3, 4, 5, 6, 7, 8)),
}
"""Name -> (function, the argument counts it takes). Spelled as sympy prints them."""

RESERVED = frozenset(CONSTANTS) | frozenset(FUNCTIONS)


def evaluate(text: str, values: Mapping[str, Value] | None = None) -> Value:
    """The value of ``text``; names come from ``values``. Raises ExprError."""
    result = _compute(parse(text), values or {})
    if isinstance(result, float) and not math.isfinite(result):
        raise ExprError("the result is not a finite number")
    return result


def to_float(value: Value) -> float:
    return float(value)


def _compute(node: Node, values: Mapping[str, Value]) -> Value:
    match node:
        case Number(value=value):
            return value
        case Name(name=name):
            return _name(name, values)
        case Unary(op=op, operand=operand):
            inner = _compute(operand, values)
            return -inner if op == "-" else inner
        case Binary(op=op, left=left, right=right):
            return _binary(op, _compute(left, values), _compute(right, values))
        case Call(function=function, args=args):
            return _call(function, [_compute(arg, values) for arg in args])
    raise ExprError(f"cannot compute {node!r}")


def _name(name: str, values: Mapping[str, Value]) -> Value:
    if name in values:
        return values[name]
    if name in CONSTANTS:
        return CONSTANTS[name]
    if name in FUNCTIONS:
        raise ExprError(f"'{name}' is a function; call it, as in {name}(x)")
    known = [*values, *CONSTANTS]
    close = difflib.get_close_matches(name, known, n=1)
    hint = f"did you mean '{close[0]}'?" if close else None
    if name == "e":
        hint = "Euler's number is written E"
    raise ExprError(f"unknown name '{name}'", hint=hint or "names come from values, pi or E")


def _binary(op: str, a: Value, b: Value) -> Value:
    try:
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            return a / b
        return _power(a, b)
    except ZeroDivisionError:
        raise ExprError("division by zero") from None
    except OverflowError:
        raise ExprError("the result is too large") from None


def _power(a: Value, b: Value) -> Value:
    if isinstance(b, Fraction) and b.denominator == 1 and isinstance(a, Fraction):
        if abs(b) > 1000:
            raise ExprError("the exponent is too large")
        return a ** int(b)
    if a < 0:
        raise ExprError("a negative number to a fractional power")
    return math.pow(float(a), float(b))


def _call(function: str, args: list[Value]) -> Value:
    if function not in FUNCTIONS:
        close = difflib.get_close_matches(function, FUNCTIONS, n=1) or [
            f for f in FUNCTIONS if f.lower() == function.lower()
        ]
        hint = f"did you mean '{close[0]}'?" if close else f"functions: {', '.join(FUNCTIONS)}"
        raise ExprError(f"unknown function '{function}'", hint=hint)
    f, counts = FUNCTIONS[function]
    if len(args) not in counts:
        wanted = " or ".join(str(n) for n in counts[:2]) + (" or more" if len(counts) > 2 else "")
        raise ExprError(f"{function} takes {wanted} arguments, got {len(args)}")
    try:
        result: Value = f(*args)
    except ExprError:
        raise  # already in our words
    except (ValueError, OverflowError) as exc:
        raise ExprError(f"{function} cannot be computed here: {exc}") from None
    return result
