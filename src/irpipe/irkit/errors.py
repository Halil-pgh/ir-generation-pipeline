"""The script's mistakes, reported at the script's own line.

    @at_the_call
    def add(self, type_name, id, /, **fields): ...      # a builder the script calls

The SDK raises a ScriptError (as a TypeError, ValueError or AttributeError)
for a mistake in how the script uses it: a field the object does not take,
a type that does not exist, a taken id, a number the IR cannot hold.
Raised deep inside the SDK, such an error would carry the SDK's own lines
in its traceback, and the orchestrator keeps only the last few lines of a
traceback (E-SCRIPT): the line of build_ir.py that made the mistake would be
cut off. ``at_the_call`` wraps what the script calls: it drops the SDK's
frames from such an error (and from a TexError, which is the script's TeX),
so the traceback ends with the script's line (underlined when the mistake is
part of it), the SDK's one ``raise`` line, and the message: six lines at
most, which is what E-SCRIPT keeps. Any other exception is a fault in the
SDK and keeps its traceback.
"""

import functools
from collections.abc import Callable

from irpipe.metrics import TexError


class ScriptError(Exception):
    """A mistake in how the script uses the SDK."""


class ScriptTypeError(ScriptError, TypeError):
    """A field the object does not take, or one it needs that is missing; a value that
    cannot go into the IR at all."""


class ScriptValueError(ScriptError, ValueError):
    """A taken id, an unknown type or space, a number the IR cannot hold."""


class ScriptAttributeError(ScriptError, AttributeError):
    """A builder for a type that does not exist."""


def at_the_call[**P, R](function: Callable[P, R]) -> Callable[P, R]:
    """``function``, raising the script's mistakes with the traceback ending at its caller."""

    @functools.wraps(function)
    def call(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return function(*args, **kwargs)
        except (ScriptError, TexError) as mistake:
            # No comment on the next line: Python would then underline it in the traceback,
            # and the orchestrator keeps only six lines (the script's, with its own
            # underline, this one, and the message).
            raise mistake.with_traceback(None) from None

    return call
