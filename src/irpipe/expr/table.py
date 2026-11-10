"""Computing a table of named values that may use each other.

    evaluate_table({"a_x": 2, "b_x": 4, "k": "a_x*b_x / (b_x*b_x)"})
    # {"a_x": Fraction(2), "b_x": Fraction(4), "k": Fraction(1, 2)}

Each value is computed after the ones it names, in any order they are
written. Values stay exact between each other, so a chain of fractions is
never rounded. A loop (``a`` uses ``b`` uses ``a``) raises CycleError.
"""

from collections.abc import Mapping
from fractions import Fraction

from irpipe.expr.errors import CycleError, ExprError
from irpipe.expr.evaluate import RESERVED, Value, evaluate
from irpipe.expr.syntax import Binary, Call, Name, Node, Unary, parse


def names_used(node: Node) -> set[str]:
    match node:
        case Name(name=name):
            return {name}
        case Unary(operand=operand):
            return names_used(operand)
        case Binary(left=left, right=right):
            return names_used(left) | names_used(right)
        case Call(args=args):
            return set().union(*(names_used(a) for a in args))
    return set()


class TableError(ExprError):
    """An error in one entry of a table; ``name`` says which."""

    def __init__(self, name: str, error: ExprError) -> None:
        super().__init__(str(error), hint=error.hint)
        self.name = name


def evaluate_table(table: Mapping[str, str | float | int]) -> dict[str, Value]:
    """Every value of ``table``, computed in the order their names need.

    Raises TableError for an entry that cannot be read or computed, and
    CycleError for values that need each other.
    """
    uses: dict[str, set[str]] = {}
    for name, written in table.items():
        if name in RESERVED:
            raise TableError(name, ExprError(f"'{name}' is a built-in name; choose another"))
        try:
            uses[name] = (
                names_used(parse(written)) & set(table) if isinstance(written, str) else set()
            )
        except ExprError as error:
            raise TableError(name, error) from None

    done: dict[str, Value] = {}

    def compute(name: str, path: list[str]) -> Value:
        if name in done:
            return done[name]
        if name in path:
            raise CycleError(path[path.index(name) :])
        for needed in sorted(uses[name]):
            compute(needed, [*path, name])
        written = table[name]
        try:
            value = evaluate(written, done) if isinstance(written, str) else Fraction(written)
        except ExprError as error:
            raise TableError(name, error) from None
        done[name] = value
        return value

    for name in table:
        compute(name, [])
    return {name: done[name] for name in table}
