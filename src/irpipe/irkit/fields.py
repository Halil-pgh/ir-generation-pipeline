"""What the builders know of the IR's models: which types there are, which fields they take,
and where a number may stay an exact expression.

    models = object_models()                      # "line" -> Line, "axes" -> Axes...
    checked(Line, "line 'a'", fields)             # TypeError: unknown or missing field
    to_json(Line, fields, values)                 # {"start": ["9/5", "12/5"], "in": "P"...}

The pydantic models of irpipe.schema (and of every registered component)
are the only description of the IR; nothing here repeats them. A field
is named as the model names it in Python (``space`` for ``"in"``); a typo
fails at the script's own line, with the closest name. Values are checked
later, all at once, by the validate stage (``pic.check()``, or the
pipeline itself), which reports them with their JSON paths.

A field whose type takes expressions (geometry, written ``Number``) gets
its exact numbers as expressions; any other field gets them as floats. The
choice is made by asking the field's own type which of the two it takes.
"""

import difflib
import functools
import json
from collections.abc import Mapping
from typing import Any, get_args

from pydantic import BaseModel, TypeAdapter, ValidationError

from irpipe.components.base import COMPONENTS
from irpipe.expr import Value
from irpipe.irkit.numbers import has_exact, plain, render
from irpipe.schema.ir import IRObject
from irpipe.schema.ir.objects import ObjectBase

FIXED = ("id", "type")
"""Fields the builder fills itself: the id is the first argument, the type the method."""


def object_models() -> dict[str, type[ObjectBase]]:
    """Every object type a builder can make: the core ones, then the registered components."""
    core: tuple[type[ObjectBase], ...] = get_args(get_args(IRObject)[0])
    models = {str(model.model_fields["type"].default): model for model in core}
    for name in COMPONENTS.names():
        models[name] = COMPONENTS.get(name)
    return models


def checked(model: type[BaseModel], what: str, fields: Mapping[str, Any]) -> dict[str, Any]:
    """``fields`` by their Python names; TypeError for a field ``model`` does not have, or a
    required one that is missing. A field given as None counts as left out."""
    names = {name: name for name in model.model_fields if name not in FIXED}
    names |= {info.alias: name for name, info in model.model_fields.items() if info.alias}
    found: dict[str, Any] = {}
    for given, value in fields.items():
        if given not in names:
            close = difflib.get_close_matches(given, list(names), n=1)
            hint = f"; did you mean '{close[0]}'?" if close else ""
            raise TypeError(f"{what} has no field '{given}'{hint}")
        if value is not None:
            found[names[given]] = value
    missing = [
        name
        for name, info in model.model_fields.items()
        if info.is_required() and name not in FIXED and name not in found
    ]
    if missing:
        raise TypeError(f"{what} needs {', '.join(missing)}")
    return found


def to_json(
    model: type[BaseModel], fields: Mapping[str, Any], values: Mapping[str, Value]
) -> dict[str, Any]:
    """``fields`` (checked, by Python name) as JSON, under the names ir.json uses."""
    written: dict[str, Any] = {}
    for name, value in fields.items():
        info = model.model_fields[name]
        written[info.alias or name] = field_json(model, name, plain(value), values)
    return written


def field_json(model: type[BaseModel], name: str, tree: Any, values: Mapping[str, Value]) -> Any:
    """One field's JSON: exact numbers as expressions if its type takes them, else as floats.

    When neither rendering is valid (the value is wrong for other reasons),
    the exact one is kept, so the validate stage reports the value as given.
    """
    exact = render(tree, exact=True)
    if not has_exact(tree) or _takes(model, name, exact, values):
        return exact
    floats = render(tree, exact=False)
    return floats if _takes(model, name, floats, values) else exact


def _takes(model: type[BaseModel], name: str, value: Any, values: Mapping[str, Value]) -> bool:
    try:
        _adapter(model, name).validate_json(
            json.dumps(value), strict=True, context={"values": dict(values)}
        )
    except ValidationError:
        return False
    return True


@functools.cache
def _adapter(model: type[BaseModel], name: str) -> TypeAdapter[Any]:
    return TypeAdapter(model.model_fields[name].rebuild_annotation())
