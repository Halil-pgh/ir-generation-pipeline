"""A shape's ``label`` becomes a text or formula of its own: ``<owner>.label``.

Normalize does this before the paint cascade, so the label is measured,
placed and drawn like any other text. The label object:

- sits at the owner's anchor (``"v.tip"``), beside it when the label gives
  ``dir``, centered on it otherwise; since it is placed by reference, it
  follows the owner wherever the owner goes;
- takes the owner's color (its stroke, else its fill) and opacity unless
  the label sets a color, and the header's ``label`` size unless it sets
  a size; it has the owner's ``z``;
- is drawn in the owner's group, right after the owner, when the owner is
  in a group; otherwise after every other object, on top.

Labels on defs are not drawn, as defs are not.
"""

from typing import Any, Final

from irpipe.frontend.paint import PaintResolver
from irpipe.schema.ir import Group, IRDocument, Label, Math, Text
from irpipe.schema.ir.objects import ObjectBase

SUFFIX: Final = ".label"


def label_id(owner: str) -> str:
    return owner + SUFFIX


def owner_of(oid: str) -> str | None:
    """The id of the object a label object belongs to; None for any other id."""
    return oid.removesuffix(SUFFIX) if oid.endswith(SUFFIX) else None


def part_of(oid: str) -> str | None:
    """The id of the object a part belongs to (``ax`` for ``ax.x_tick_3``); None for a plain
    id and for a label, which has its own path.

    A component opens into parts with dotted ids (irpipe/components); a part
    is reported at its component's place in the agent's file.
    """
    whole, dot, _ = oid.partition(".")
    return whole if dot and owner_of(oid) is None else None


def label_ids(document: IRDocument) -> list[str]:
    """The ids the document's labels will have."""
    return [label_id(obj.id) for obj in document.objects if getattr(obj, "label", None)]


def with_labels(document: IRDocument, resolver: PaintResolver) -> IRDocument:
    """``document`` with every object's label drawn as an object of its own."""
    parent = {
        child: obj.id
        for obj in document.objects
        if isinstance(obj, Group)
        for child in obj.children
    }
    labels: list[Text | Math] = []
    after: dict[str, list[str]] = {}  # group id -> owners whose label joins that group
    for obj in document.objects:
        label = getattr(obj, "label", None)
        if label is None:
            continue
        labels.append(_label_object(obj, label, resolver))
        if obj.id in parent:
            after.setdefault(parent[obj.id], []).append(obj.id)
    if not labels:
        return document
    objects = [
        _with_label_children(obj, after[obj.id]) if obj.id in after else obj
        for obj in document.objects
    ]
    return document.model_copy(update={"objects": (*objects, *labels)})


def _label_object(owner: ObjectBase, label: Label, resolver: PaintResolver) -> Text | Math:
    """The label as an object; built without validation, since its id has a dot."""
    paint = resolver.paint(owner)
    fields: dict[str, Any] = {
        "id": label_id(owner.id),
        "at": f"{owner.id}.{label.at}",
        "dir": label.dir,
        "gap": label.gap,
        "size": label.size or "label",
        "color": label.color or paint.color or paint.fill,
        "opacity": None if paint.opacity == 1 else paint.opacity,
        "z": owner.z,
    }
    if label.text is not None:
        fields |= {"text": label.text, "weight": label.weight, "italic": label.italic}
        return Text.model_construct(None, **fields)
    return Math.model_construct(None, **fields, tex=label.tex or "")


def _with_label_children(group: ObjectBase, owners: list[str]) -> ObjectBase:
    assert isinstance(group, Group)
    children: list[str] = []
    for child in group.children:
        children.append(child)
        if child in owners:
            children.append(label_id(child))
    return group.model_copy(update={"children": tuple(children)})


def source_paths(document: IRDocument) -> dict[str, str]:
    """Each object's and def's JSON path in the agent's file.

    A label's path is its owner's with ``.label`` added; a component's part's
    is its component's.
    """
    paths = {obj.id: f"defs[{k}]" for k, obj in enumerate(document.defs)}
    for k, obj in enumerate(document.objects):
        owner, whole = owner_of(obj.id), part_of(obj.id)
        if owner in paths:
            paths[obj.id] = f"{paths[owner]}.label"
        elif whole in paths:
            paths[obj.id] = paths[whole]
        else:
            paths[obj.id] = f"objects[{k}]"
    return paths
