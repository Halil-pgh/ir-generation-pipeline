"""Reading components in ir.json, and opening them into core objects.

    model = document_model()              # IRDocument that also takes every registered component
    document = model.model_validate_json(text, context={"values": values})
    core, issues = expand_components(document, values)

The core IR schema (schema/ir) does not change: ``document_model`` derives
from IRDocument a model whose ``objects`` may also hold the components that
are registered, so an unknown type is still reported with a suggestion, now
among the components too. ``expand_components`` replaces each component, in
its own place, by its root, and puts its parts at the end of ``objects``,
where they do not move any other object's JSON path. The document it hands
on is a plain IRDocument holding core objects only.
"""

import functools
import operator
from collections.abc import Iterable, Mapping
from typing import Annotated, Any, get_args

from pydantic import Field, create_model

from irpipe.components.base import (
    COMPONENTS,
    E_COMPONENT,
    Component,
    ComponentError,
    Context,
)
from irpipe.core import Issue
from irpipe.expr import Value
from irpipe.frontend.labels import part_of
from irpipe.schema.ir import IRDocument
from irpipe.schema.ir.objects import IRObject, ObjectBase


def document_model() -> type[IRDocument]:
    """IRDocument whose objects may also be the registered components (IRDocument when none)."""
    return _model_for(tuple(COMPONENTS.get(name) for name in COMPONENTS.names()))


@functools.cache
def _model_for(components: tuple[type[Component], ...]) -> type[IRDocument]:
    if not components:
        return IRDocument
    core = get_args(get_args(IRObject)[0])  # the members of the core union
    members: Any = functools.reduce(operator.or_, (*core, *components))
    body_object = Annotated[members, Field(discriminator="type")]
    model: type[IRDocument] = create_model(
        "IRDocumentWithComponents",
        __base__=IRDocument,
        __doc__="A whole ir.json whose objects may also be components (irpipe/components).",
        objects=(tuple[body_object, ...], ()),
    )
    return model


def expand_components(
    document: IRDocument, values: Mapping[str, Value]
) -> tuple[IRDocument, list[Issue]]:
    """``document`` with every component opened, or the issues that stopped one."""
    if not any(isinstance(obj, Component) for obj in document.objects):
        return document, []
    context = Context(values, {space.id: space.units for space in document.spaces})
    objects: list[ObjectBase] = []
    parts: list[ObjectBase] = []
    issues: list[Issue] = []
    for k, obj in enumerate(document.objects):
        if not isinstance(obj, Component):
            objects.append(obj)
            continue
        try:
            expansion = obj.expand(context)
        except ComponentError as error:
            where = f"objects[{k}]" + (f".{error.field}" if error.field else "")
            issues.append(error.code(str(error), path=where, objects=[obj.id], hint=error.hint))
            continue
        objects.append(expansion.root)
        parts.extend(expansion.parts)
    if issues:
        return document, issues
    fields = {name: getattr(document, name) for name in IRDocument.model_fields}
    fields["objects"] = (*objects, *parts)
    return IRDocument.model_construct(**fields), []


def said_once(issues: Iterable[Issue]) -> list[Issue]:
    """Issues about a component's parts, said once and about the component.

    The parts share the component's fields, so one wrong name (a space, a
    style, a color) would come back once per part. An issue that names a
    part is told of the component instead (``'ax.x_tick_3'`` -> ``'ax'``),
    and a second one just like it is dropped. Other issues pass unchanged.
    """
    seen: set[tuple[str, str | None, str]] = set()
    kept: list[Issue] = []
    for issue in issues:
        parts = {oid: whole for oid in issue.objects if (whole := part_of(oid)) is not None}
        if parts:
            message = issue.message
            for oid, whole in parts.items():
                message = message.replace(f"'{oid}'", f"'{whole}'")
            objects = tuple(dict.fromkeys(parts.get(oid, oid) for oid in issue.objects))
            issue = issue.model_copy(update={"message": message, "objects": objects})
            key = (issue.code, issue.path, issue.message)
            if key in seen:
                continue
            seen.add(key)
        kept.append(issue)
    return kept


__all__ = ["E_COMPONENT", "document_model", "expand_components", "said_once"]
