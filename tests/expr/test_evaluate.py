"""The expression language: what it reads, what it computes, and how it says no."""

import math
from fractions import Fraction

import pytest

from irpipe.expr import ExprError, evaluate, parse


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("44/17", Fraction(44, 17)),
        ("44/17*17", 44),  # exact: no rounding on the way
        ("0.1 + 0.2", Fraction(3, 10)),  # 0.30000000000000004 in floats
        ("1.5e-3", Fraction(3, 2000)),
        ("2 + 3*4", 14),
        ("(2 + 3)*4", 20),
        ("2**3**2", 512),  # right to left: 2**9
        ("-2**2", -4),  # the power binds first
        ("2**-1", Fraction(1, 2)),
        ("sqrt(9/4)", Fraction(3, 2)),  # a perfect square stays exact
        ("Abs(-3)", 3),
        ("Min(3, 1, 2)", 1),
        ("Max(3, 1, 2)", 3),
    ],
)
def test_arithmetic_stays_exact(text: str, value: Fraction | int) -> None:
    result = evaluate(text)
    assert isinstance(result, Fraction)
    assert result == value


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("sqrt(2)/2", math.sqrt(2) / 2),
        ("2*pi/3", 2 * math.pi / 3),
        ("-sqrt(3)/2", -math.sqrt(3) / 2),
        ("3*sqrt(5)/5", 3 * math.sqrt(5) / 5),
        ("180*atan2(3, 2)/pi", math.degrees(math.atan2(3, 2))),
        ("E**2", math.e**2),
        ("log(8, 2)", 3),
        ("cos(pi)", -1),
        ("asin(1)", math.pi / 2),
    ],
)
def test_what_sympy_prints_is_understood(text: str, value: float) -> None:
    assert evaluate(text) == pytest.approx(value)


def test_names_come_from_the_values_given() -> None:
    assert evaluate("k*b_x", {"k": Fraction(1, 2), "b_x": Fraction(4)}) == 2


@pytest.mark.parametrize(
    ("text", "message", "hint"),
    [
        ("2^3", "unexpected '^' at character 2", "write powers with **"),
        ("2*(3", "expected ')' at character 5, found the end", None),
        ("2 3", "expected the end of the expression at character 3, found '3'", None),
        ("a.b", "unexpected '.' at character 2", None),
        ("", "the expression is empty", None),
        ("1/0", "division by zero", None),
        ("sqrt(-1)", "square root of a negative number", None),
        ("(-8)**(1/3)", "a negative number to a fractional power", None),
        ("asin(2)", "asin needs a number between -1 and 1", None),
        ("log(0)", "log needs a positive number (and a positive base other than 1)", None),
        ("10**10000", "the exponent is too large", None),
        ("exp(1000)", "exp cannot be computed here: math range error", None),
        ("atan2(1)", "atan2 takes 2 arguments, got 1", None),
        ("abs(-1)", "unknown function 'abs'", "did you mean 'Abs'?"),
        ("e", "unknown name 'e'", "Euler's number is written E"),
        ("sin", "'sin' is a function; call it, as in sin(x)", None),
        ("pii", "unknown name 'pii'", "did you mean 'pi'?"),
    ],
)
def test_a_bad_expression_says_why(text: str, message: str, hint: str | None) -> None:
    with pytest.raises(ExprError) as caught:
        evaluate(text)
    assert str(caught.value) == message
    assert caught.value.hint == hint


def test_nothing_but_arithmetic_is_read() -> None:
    for text in ["__import__('os')", "x.__class__", "[1, 2]", "'a'", "lambda: 1"]:
        with pytest.raises(ExprError):
            parse(text)
