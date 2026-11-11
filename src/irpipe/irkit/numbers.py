"""Numbers as the IR should get them: exact where the script has them exact.

    plain(Fraction(44, 17))     -> Exact("44/17", 2.588...)
    plain(sympy.sqrt(2) / 2)    -> Exact("sqrt(2)/2", 0.707...)
    plain(0.5), plain(3)        -> 0.5, 3
    render(tree, exact=True)    -> JSON, exact numbers as expressions ("44/17")
    render(tree, exact=False)   -> JSON, exact numbers as floats

``plain`` turns what a script hands a builder into a JSON tree whose exact
numbers are still marked (``Exact``); ``render`` writes the tree out. Which
of the two renderings a field gets is chosen field by field (fields.py):
only geometry numbers may be expressions, so a stroke width or an opacity
gets the float.

- A Fraction is written as its expression (``"44/17"``), a whole one as an int.
- A sympy number is written as sympy prints it (``"sqrt(2)/2"``, ``"pi/4"``)
  when the IR's expression language reads that back to the same value;
  otherwise (``sec(1)``, or a form irpipe/expr refuses) as a float. A sympy
  expression with symbols left in it, or one that is not a finite real
  number, is refused at the line that hands it over.
- A handle (an object, a space, a zone) becomes its id.
- numpy numbers and arrays become Python numbers and lists; any other
  iterable becomes a list.
"""

import math
import numbers
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from pydantic import BaseModel

from irpipe.expr import ExprError, evaluate
from irpipe.irkit.handles import Handle

SAME = 1e-9
"""Relative difference within which a printed sympy number reads back as the same value."""


@dataclass(frozen=True)
class Exact:
    """An exact number: the expression the IR gets, and its value as a float."""

    text: str
    value: float


def plain(value: object) -> Any:
    """``value`` as a JSON tree, with exact numbers marked; TypeError or ValueError if it
    cannot go into the IR."""
    if value is None or isinstance(value, bool | str):
        return value
    if isinstance(value, Handle):
        return value.id
    if isinstance(value, Fraction):
        return value.numerator if value.denominator == 1 else Exact(str(value), float(value))
    if isinstance(value, numbers.Integral):
        return int(value)
    if _is_sympy(value):
        return _from_sympy(value)
    if isinstance(value, numbers.Real):
        return _finite(float(value), value)
    if isinstance(value, BaseModel):
        return plain(value.model_dump(by_alias=True, exclude_none=True))
    if isinstance(value, Mapping):
        return {str(key): plain(item) for key, item in value.items() if item is not None}
    if hasattr(value, "tolist"):  # a numpy array or number
        return plain(value.tolist())
    if isinstance(value, Iterable):
        return [plain(item) for item in value]
    raise TypeError(f"{type(value).__name__} {value!r} cannot go into the IR")


def render(tree: Any, *, exact: bool) -> Any:
    """``tree`` as JSON: exact numbers as their expressions, or as floats."""
    if isinstance(tree, Exact):
        return tree.text if exact else tree.value
    if isinstance(tree, dict):
        return {key: render(item, exact=exact) for key, item in tree.items()}
    if isinstance(tree, list):
        return [render(item, exact=exact) for item in tree]
    return tree


def has_exact(tree: Any) -> bool:
    """True when ``tree`` holds an exact number that is not a whole one."""
    if isinstance(tree, Exact):
        return True
    if isinstance(tree, dict):
        return any(has_exact(item) for item in tree.values())
    if isinstance(tree, list):
        return any(has_exact(item) for item in tree)
    return False


def _finite(number: float, given: object) -> float:
    if not math.isfinite(number):
        raise ValueError(f"{given!r} is not a finite number, so it cannot go into the IR")
    return number


def _is_sympy(value: object) -> bool:
    """A sympy object, told apart without importing sympy (the SDK does not need it)."""
    return type(value).__module__.startswith("sympy.") and hasattr(value, "free_symbols")


def _from_sympy(value: Any) -> Any:
    if value.free_symbols:
        names = ", ".join(sorted(str(symbol) for symbol in value.free_symbols))
        raise ValueError(
            f"the sympy expression {value} still holds {names}; put numbers in first (.subs)"
        )
    if value.is_Integer:
        return int(value)
    if value.is_Rational:
        return plain(Fraction(int(value.p), int(value.q)))
    try:
        number = complex(value.evalf(17))
    except TypeError:
        raise ValueError(f"the sympy expression {value} is not a number") from None
    if number.imag != 0:
        raise ValueError(f"{value} is not a real number, so it cannot go into the IR")
    real = _finite(number.real, value)
    if value.is_Float:
        return real
    text = str(value)
    try:
        back = float(evaluate(text, {}))
    except ExprError:
        return real  # sympy printed something the IR's expressions do not read
    return Exact(text, real) if math.isclose(back, real, rel_tol=SAME, abs_tol=SAME) else real
