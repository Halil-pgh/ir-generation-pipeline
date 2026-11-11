"""Numbers on their way into the IR: exact ones stay exact, the rest become plain JSON."""

import math
from fractions import Fraction
from typing import Any

import pytest

from irpipe.irkit import Handle
from irpipe.irkit.numbers import Exact, has_exact, plain, render


def test_a_fraction_becomes_its_expression_and_a_whole_one_an_int() -> None:
    assert plain(Fraction(44, 17)) == Exact("44/17", 44 / 17)
    assert plain(Fraction(-3, 4)) == Exact("-3/4", -0.75)
    assert plain(Fraction(8, 2)) == 4
    assert isinstance(plain(Fraction(8, 2)), int)


def test_a_tree_is_written_with_its_exact_numbers_or_as_floats() -> None:
    tree = plain({"center": (Fraction(9, 5), 0), "radius": 0.5, "dash": None, "on": True})
    assert render(tree, exact=True) == {"center": ["9/5", 0], "radius": 0.5, "on": True}
    assert render(tree, exact=False) == {"center": [1.8, 0], "radius": 0.5, "on": True}
    assert has_exact(tree) and not has_exact(plain([1, 2.5, "a.tip"]))


def test_handles_arrays_and_iterables_become_plain_json() -> None:
    numpy = pytest.importorskip("numpy")
    a = Handle("a", "line")
    assert plain([a, (x * x for x in range(3)), numpy.array([[1.5, 2]])]) == [
        "a", [0, 1, 4], [[1.5, 2.0]],
    ]  # fmt: skip
    assert plain(numpy.float64(0.25)) == 0.25 and plain(numpy.int64(3)) == 3


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_a_number_that_is_not_finite_is_refused(bad: float) -> None:
    with pytest.raises(ValueError, match="not a finite number"):
        plain([0, bad])


def test_something_that_is_not_json_is_refused() -> None:
    with pytest.raises(TypeError, match=r"object .* cannot go into the IR"):
        plain(object())


# sympy (the SDK does not need it; scripts may use it)


@pytest.mark.parametrize(
    ("made", "expected"),
    [
        (lambda sp: sp.Rational(44, 17), Exact("44/17", 44 / 17)),
        (lambda sp: sp.Integer(4), 4),
        (lambda sp: sp.sqrt(2) / 2, Exact("sqrt(2)/2", math.sqrt(2) / 2)),
        (lambda sp: 180 * sp.atan2(3, 2) / sp.pi, Exact("180*atan(3/2)/pi", 56.309932474020215)),
        (lambda sp: sp.Float(1.5), 1.5),
        # what irpipe/expr does not read becomes a float of the same value
        (lambda sp: sp.sec(1), 1 / math.cos(1)),
        (lambda sp: (sp.sqrt(2) - 2) ** 2, (math.sqrt(2) - 2) ** 2),  # S8 in the plan
    ],
)
def test_a_sympy_number_is_written_as_sympy_prints_it_when_the_ir_reads_that(
    made: Any, expected: Any
) -> None:
    sp = pytest.importorskip("sympy")
    found = plain(made(sp))
    if isinstance(expected, Exact):
        assert isinstance(found, Exact) and found.text == expected.text
        assert found.value == pytest.approx(expected.value, rel=1e-12)
    else:
        assert type(found) is type(expected) and found == pytest.approx(expected, rel=1e-12)


def test_a_sympy_expression_that_is_not_a_finite_real_number_is_refused() -> None:
    sp = pytest.importorskip("sympy")
    with pytest.raises(ValueError, match="still holds x; put numbers in first"):
        plain(sp.Symbol("x") + 1)
    with pytest.raises(ValueError, match="not a real number"):
        plain(1 + sp.I)
    with pytest.raises(ValueError, match="not a finite number"):
        plain(sp.oo)
