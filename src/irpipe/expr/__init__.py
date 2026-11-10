"""The IR's expression language: exact numbers written as text, never run as code.

Wherever the IR takes a number for geometry, it also takes an expression:

    "radius": "sqrt(2)/2"        "end_angle": "180*atan2(3, 2)/pi"
    "center": ["44/17", "k*b_x"]  with  "values": {"b_x": 4, "k": "1/2"}

The language is what sympy prints: numbers, ``+ - * / **``, parentheses,
``pi`` and ``E``, and the functions sqrt, sin, cos, tan, asin, acos, atan,
atan2, exp, log, Abs, Min, Max. Names refer to the IR's ``values`` table.
Text is parsed by a small parser of our own; nothing is ever passed to
Python's eval (analysis §4).

Module map:
    syntax.py    text -> tokens -> syntax tree
    evaluate.py  syntax tree -> exact value (fractions where possible)
    table.py     a table of named values that use each other, loops refused
    errors.py    ExprError, CycleError
"""

from irpipe.expr.errors import CycleError, ExprError
from irpipe.expr.evaluate import CONSTANTS, FUNCTIONS, RESERVED, Value, evaluate
from irpipe.expr.syntax import parse
from irpipe.expr.table import TableError, evaluate_table, names_used

__all__ = [
    "CONSTANTS",
    "FUNCTIONS",
    "RESERVED",
    "CycleError",
    "ExprError",
    "TableError",
    "Value",
    "evaluate",
    "evaluate_table",
    "names_used",
    "parse",
]
