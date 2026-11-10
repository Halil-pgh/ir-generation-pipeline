"""Named values: computed in the order they need, exact between each other, never in a loop."""

from fractions import Fraction

import pytest

from irpipe.expr import CycleError, TableError, evaluate_table


def test_values_may_use_each_other_in_any_order() -> None:
    table: dict[str, str | int] = {
        "k": "(a_x*b_x + a_y*b_y) / (b_x**2 + b_y**2)",
        "a_x": 2,
        "a_y": 3,
        "b_x": 4,
        "b_y": 0,
    }
    assert evaluate_table(table)["k"] == Fraction(1, 2)


def test_a_chain_of_fractions_is_never_rounded() -> None:
    table = {"third": "1/3", "back": "third*3", "check": "back - 1"}
    assert evaluate_table(table)["check"] == 0


@pytest.mark.parametrize(
    ("table", "loop"),
    [
        ({"a": "a + 1"}, ["a"]),
        ({"a": "b + 1", "b": "a*2"}, ["a", "b"]),
        ({"x": 1, "a": "c", "b": "a", "c": "b + x"}, ["a", "c", "b"]),
    ],
)
def test_a_loop_is_named_in_order(table: dict[str, str | int], loop: list[str]) -> None:
    with pytest.raises(CycleError) as caught:
        evaluate_table(table)
    assert caught.value.loop == loop
    assert str(caught.value).startswith("values refer to each other in a loop: ")


def test_a_bad_entry_is_named() -> None:
    with pytest.raises(TableError) as caught:
        evaluate_table({"ok": 1, "bad": "ok/0"})
    assert (caught.value.name, str(caught.value)) == ("bad", "division by zero")


@pytest.mark.parametrize("name", ["pi", "E", "sqrt"])
def test_built_in_names_cannot_be_values(name: str) -> None:
    with pytest.raises(TableError, match="is a built-in name"):
        evaluate_table({name: 3})
