"""Checks the IR's expressions and computes its named values.

    E-EXPR    an expression cannot be read or computed (a typo, sqrt(-1), 1/0)
    E-CYCLE   named values refer to each other in a loop

The ``values`` table is computed first, straight from the JSON, so that the
schema check can hand the values to every expression in the geometry. An
expression there that fails comes back from the schema check as E-EXPR, with
the path of the field it was written in.
"""

from typing import Any

from irpipe.core import ISSUE_CODES, Issue, IssueCode, Origin
from irpipe.expr import CycleError, TableError, Value, evaluate_table

E_EXPR = ISSUE_CODES.register(
    IssueCode("E-EXPR", Origin.IR, "an expression cannot be read or computed")
)
E_CYCLE = ISSUE_CODES.register(
    IssueCode("E-CYCLE", Origin.IR, "named values refer to each other in a loop")
)


def computed_values(raw: Any) -> tuple[dict[str, Value], list[Issue]]:
    """The IR's ``values``, computed exactly, or the issue that stopped them.

    A table whose form is wrong (not an object, a value that is neither a
    number nor a string) is left to the schema check, which reports it.
    """
    table = raw.get("values") if isinstance(raw, dict) else None
    if not isinstance(table, dict) or not all(
        isinstance(value, str | int | float) and not isinstance(value, bool)
        for value in table.values()
    ):
        return {}, []
    try:
        return evaluate_table(table), []
    except CycleError as error:
        loop = error.loop
        return {}, [E_CYCLE(str(error), path=f"values.{loop[0]}", hint=error.hint)]
    except TableError as error:
        return {}, [E_EXPR(str(error), path=f"values.{error.name}", hint=error.hint)]
