"""The IR as the agent reads it: every object type and its fields, written from the models.

    text = object_reference()

Analysis §4: the spec is generated from the schema, so it never drifts
from what validate accepts. Each type (the core ones, then the registered
components) gets its docstring and its own fields; what every object
shares is written once. Fields are named as irkit's builders take them
(``space``, which is ``"in"`` in ir.json). Types are written short, with a
legend for the ones that recur (``point``, ``color``...).
"""

import inspect
import json
import types
import typing
from typing import Annotated, Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from irpipe.components.base import Component
from irpipe.irkit.fields import object_models
from irpipe.schema.color import ColorRef
from irpipe.schema.ir import Anchor, Direction, Label, Point, RegionShape, Size, Subpath
from irpipe.schema.ir import objects as objects_module
from irpipe.schema.ir.common import _compute
from irpipe.schema.ir.objects import CubicTo, InSpace, LineTo, ObjectBase, QuadTo

ALIASES: tuple[tuple[Any, str], ...] = (
    (Point, "point"),
    (ColorRef, "color"),
    (Direction, "dir"),
    (Size, "size"),
    (RegionShape, "region"),
    (Anchor, "anchor"),
)
LEGEND = """\
Types: number = a number, or an expression the IR computes exactly ("44/17",
"sqrt(2)/2"; irkit writes Fractions this way); float = a plain number;
point = [x, y], "id.anchor" (from a handle: a.tip), or a point on an outline
(f.at(t=0.5), f.at(x=2)); color = "#RRGGBB", [r, g, b], a header or extra color
name, or "none"; size = "title" | "heading" | "body" | "label" | "caption", or
reference pixels; dir = a direction name ("up_right"...), degrees, or [dx, dy];
anchor = a point of a box ("left_baseline", "center"...); region = an id, or
{"union"/"intersection"/"difference"/"xor": [...]}, {"half_plane": [p, q]},
{"under": f, "x": [a, b]}, {"between": [f, g], "x": [a, b]} (irkit: union(),
difference(), under()...); [T, ...] = a list of T."""

SHARED = (ObjectBase, InSpace)
"""Models whose fields every object (or every component) has; written once."""
PARTS: tuple[type[BaseModel], ...] = (Label, Subpath, LineTo, QuadTo, CubicTo)
"""Models that are the value of a field (``label``, a path's ``subpaths``), written after
the objects."""


def object_reference() -> str:
    """Every object type with its docstring and fields, after what all of them share."""
    lines = [LEGEND, "", inspect.getdoc(objects_module) or "", "", "Every object takes:"]
    lines += _fields(InSpace, own_only=False, skip=("id", "type"))
    lines.append("  (space is not taken by group and stack; components all take it)")
    for name, model in object_models().items():
        kind = "component" if issubclass(model, Component) else "object"
        lines += ["", f"## {name} ({kind})"]
        lines += [doc] if (doc := _doc(model)) else []
        lines += _fields(model, own_only=True)
    for part in PARTS:
        lines += ["", f"## {part.__name__} (the value of a field)"]
        lines += [doc] if (doc := _doc(part)) else []
        lines += _fields(part, own_only=False)
    return "\n".join(lines) + "\n"


def _doc(model: type[BaseModel]) -> str:
    """The model's own docstring (not one it inherits); a component's module docstring."""
    if issubclass(model, Component):  # its module's docstring is its documentation
        return inspect.getdoc(inspect.getmodule(model)) or ""
    own = model.__dict__.get("__doc__")
    return inspect.cleandoc(own) if isinstance(own, str) else ""


def _fields(model: type[BaseModel], own_only: bool, skip: tuple[str, ...] = ()) -> list[str]:
    shared = {name for base in SHARED for name in base.model_fields}
    lines = []
    for name, info in model.model_fields.items():
        if name in ("id", "type", *skip) or (own_only and name in shared):
            continue
        lines.append(f"  {name}: {type_text(info)}{_default(info)}")
    return lines


def _default(info: FieldInfo) -> str:
    if info.is_required():
        return " (required)"
    default = info.default
    if info.default_factory is not None or default in (None, (), [], {}):
        return ""
    written = repr(default) if isinstance(default, BaseModel) else json.dumps(default)
    return f" = {written}"


def type_text(info: FieldInfo) -> str:
    """A field's type, short."""
    return _text(info.annotation, info.metadata)


def _text(annotation: Any, metadata: Any = ()) -> str:
    named = _alias(annotation)
    if named:
        return named
    if any(getattr(m, "func", None) is _compute for m in metadata):
        return "number"
    if isinstance(annotation, typing.TypeAliasType):
        return _text(annotation.__value__)
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is Annotated:
        return _text(args[0], args[1:])
    if origin in (Union, types.UnionType):
        kept = tuple(a for a in args if a is not type(None))
        named = _alias(kept[0] if len(kept) == 1 else Union[kept])  # noqa: UP007
        if named:
            return named
        return " | ".join(dict.fromkeys(_text(a) for a in kept))
    if origin is Literal:
        return " | ".join(json.dumps(a) for a in args)
    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return f"[{_text(args[0])}, ...]"
        return "[" + ", ".join(_text(a) for a in args) + "]"
    if origin is dict:
        return f"{{{_text(args[0])}: {_text(args[1])}}}"
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation.__name__
    simple = {float: "float", int: "int", str: "string", bool: "bool"}
    return simple.get(annotation, str(annotation))


def _alias(annotation: Any) -> str | None:
    """The legend's short name for ``annotation`` (a union compares by its members)."""
    for alias, name in ALIASES:
        if annotation == alias:
            return name
        if get_origin(alias) in (Union, types.UnionType) and get_origin(annotation) in (
            Union, types.UnionType,
        ) and set(get_args(annotation)) == set(get_args(alias)):  # fmt: skip
            return name
    return None
