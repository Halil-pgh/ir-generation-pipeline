"""Checks that every name in the IR points at something, and that groups nest properly.

The schema has already checked the form of every field; this module checks
what the names mean:

- E-ID: two objects, defs, spaces or zones share an id, or one is called
  ``frame`` or ``safe``.
- E-REF: a name points at nothing: an object in ``focus``, a group or a
  stack, a style class, a color, a space (``in``), the object of
  ``next_to``, or a reference: ``"v.tip"`` to an object, zone, ``frame`` or
  ``safe`` that has no such point, ``{"on": ...}`` to something with no
  outline.
- E-GROUP: groups and stacks are put together wrongly: an object in two of
  them, one that contains itself, or a def (which is never drawn) inside.
"""

import difflib
from collections.abc import Collection, Iterator

from irpipe.core import ISSUE_CODES, Issue, IssueCode, Origin
from irpipe.frontend.anchors import (
    BASELINE_ANCHORS,
    BOX_ANCHORS,
    RESERVED,
    anchor_names,
    references,
    split_ref,
)
from irpipe.frontend.labels import label_id
from irpipe.schema.color import NO_PAINT
from irpipe.schema.ir import Container, IRDocument, OnRef, Shape
from irpipe.schema.ir.objects import ObjectBase

E_ID = ISSUE_CODES.register(IssueCode("E-ID", Origin.IR, "two things in the IR share an id"))
E_REF = ISSUE_CODES.register(
    IssueCode(
        "E-REF",
        Origin.IR,
        "a name points at nothing: no such object, point, space, style or color",
    )
)
E_GROUP = ISSUE_CODES.register(
    IssueCode(
        "E-GROUP",
        Origin.IR,
        "a group or stack is built wrongly: shared child, a loop, or a def inside",
    )
)


def reference_issues(document: IRDocument) -> list[Issue]:
    """Every E-ID, E-REF and E-GROUP problem of ``document``, in file order."""
    issues = list(_duplicate_ids(document))
    if issues:
        return issues  # with ids in doubt, references cannot be judged
    issues.extend(_focus(document))
    issues.extend(_styles_and_colors(document))
    issues.extend(_groups(document))
    issues.extend(_places(document))
    return issues


def body_objects(document: IRDocument) -> Iterator[tuple[str, ObjectBase]]:
    """Every object and def with its JSON path."""
    for k, obj in enumerate(document.defs):
        yield f"defs[{k}]", obj
    for k, obj in enumerate(document.objects):
        yield f"objects[{k}]", obj


def _duplicate_ids(document: IRDocument) -> Iterator[Issue]:
    first: dict[str, str] = {}
    named = [(f"spaces[{k}].id", space.id) for k, space in enumerate(document.spaces)]
    named += [(f"zones.{name}", name) for name in document.zones]
    named += [(f"{path}.id", obj.id) for path, obj in body_objects(document)]
    for path, oid in named:
        if oid in RESERVED:
            yield E_ID(
                f"'{oid}' names the picture's own box and cannot be an id",
                path=path,
                hint=f"'{oid}.center' and the like already refer to it; choose another id",
            )
        elif oid in first:
            yield E_ID(
                f"id '{oid}' is already used by {first[oid]}",
                path=path,
                objects=[oid],
                hint="give every object, def, space and zone its own id",
            )
        else:
            first[oid] = path.removesuffix(".id")


def _focus(document: IRDocument) -> Iterator[Issue]:
    objects = {obj.id for obj in document.objects}
    for k, oid in enumerate(document.focus):
        if oid not in objects:
            yield E_REF(
                f"focus names '{oid}', which is not an object",
                path=f"focus[{k}]",
                hint=_did_you_mean(oid, objects),
            )


def _styles_and_colors(document: IRDocument) -> Iterator[Issue]:
    header_colors = set(document.colors)
    for name, style in document.styles.items():
        for field in ("color", "fill"):
            yield from _color(getattr(style, field), header_colors, f"styles.{name}.{field}")
    for name, extra in document.extra_colors.items():
        if not isinstance(extra, str | tuple):
            for k, part in enumerate(extra.mix):
                yield from _color(part, header_colors, f"extra_colors.{name}.mix[{k}]", mixing=True)
    all_colors = header_colors | set(document.extra_colors)
    for path, obj in body_objects(document):
        for k, class_name in enumerate(obj.style_names):
            if class_name not in document.styles:
                where = f"{path}.style" if isinstance(obj.style, str) else f"{path}.style[{k}]"
                yield E_REF(
                    f"style class '{class_name}' is not in the header's styles",
                    path=where,
                    objects=[obj.id],
                    hint=_did_you_mean(class_name, document.styles)
                    or f"style classes: {', '.join(document.styles) or 'none'}",
                )
        for field in ("color", "fill"):
            yield from _color(getattr(obj, field, None), all_colors, f"{path}.{field}", obj.id)


def _color(
    value: object,
    known: Collection[str],
    path: str,
    owner: str | None = None,
    *,
    mixing: bool = False,
) -> Iterator[Issue]:
    """An E-REF when ``value`` is a color name that is not defined."""
    if not isinstance(value, str) or value.startswith("#"):
        return
    if value == NO_PAINT:
        if mixing:
            yield E_REF("a mix needs two colors, and 'none' is no color", path=path)
        return
    if value not in known:
        where = "the header's colors" if mixing or path.startswith("styles") else "colors"
        yield E_REF(
            f"color '{value}' is not defined in {where}",
            path=path,
            objects=[owner] if owner else (),
            hint=_did_you_mean(value, known)
            or "write a literal color, or a name from colors or extra_colors",
        )


def _groups(document: IRDocument) -> Iterator[Issue]:
    objects = {obj.id for obj in document.objects}
    defs = {obj.id for obj in document.defs}
    parent: dict[str, str] = {}
    kind: dict[str, str] = {}
    for k, group in enumerate(document.objects):
        if not isinstance(group, Container):
            continue
        gid, what, seen = group.id, group.type, set[str]()
        kind[gid] = what
        for j, child in enumerate(group.children):
            where = f"objects[{k}].children[{j}]"
            if child == gid:
                yield E_GROUP(f"{what} '{gid}' lists itself", path=where, objects=[gid])
            elif child in seen:
                yield E_GROUP(
                    f"{what} '{gid}' lists '{child}' twice", path=where, objects=[gid, child]
                )
            elif child in defs:
                yield E_GROUP(
                    f"{what} '{gid}' lists def '{child}'; defs are never drawn",
                    path=where,
                    objects=[gid, child],
                    hint=f"move the object from defs to objects, or leave it out of the {what}",
                )
            elif child not in objects:
                yield E_REF(
                    f"{what} '{gid}' lists '{child}', which is not an object",
                    path=where,
                    objects=[gid],
                    hint=_did_you_mean(child, objects),
                )
            elif child in parent:
                yield E_GROUP(
                    f"'{child}' is already in {kind[parent[child]]} '{parent[child]}'; "
                    "an object belongs to at most one group or stack",
                    path=where,
                    objects=[gid, child, parent[child]],
                )
            else:
                parent[child] = gid
            seen.add(child)
    groups = {obj.id: f"objects[{k}]" for k, obj in enumerate(document.objects)}
    yield from _loops(parent, groups)


def _loops(parent: dict[str, str], paths: dict[str, str]) -> Iterator[Issue]:
    reported: set[str] = set()
    for start in parent:
        chain, node = [start], parent.get(start)
        while node is not None and node not in chain:
            chain.append(node)
            node = parent.get(node)
        if node is None or node in reported:
            continue
        loop = chain[chain.index(node) :]
        reported.update(loop)
        yield E_GROUP(
            "groups or stacks contain each other: " + " -> ".join([*reversed(loop), loop[-1]]),
            path=paths[loop[-1]],
            objects=loop,
            hint="a group or stack may not end up inside itself",
        )


def _places(document: IRDocument) -> Iterator[Issue]:
    """References, spaces, ``next_to`` and label points name things that exist."""
    points: dict[str, tuple[str, ...]] = {
        name: BOX_ANCHORS for name in (*document.zones, *RESERVED)
    }
    outlined: set[str] = set()
    for _, obj in body_objects(document):
        points[obj.id] = anchor_names(obj)
        if isinstance(obj, Shape):
            outlined.add(obj.id)
        if getattr(obj, "label", None) is not None:
            points[label_id(obj.id)] = BOX_ANCHORS + BASELINE_ANCHORS
    spaces = {space.id for space in document.spaces}
    for k, space in enumerate(document.spaces):
        if not isinstance(space.origin, tuple):
            yield from _reference(space.origin, f"spaces[{k}].origin", None, points, outlined)
    for path, obj in body_objects(document):
        for where, ref in references(obj):
            yield from _reference(ref, f"{path}.{where}", obj.id, points, outlined)
        drawn_in = getattr(obj, "space", None)
        if drawn_in is not None and drawn_in not in spaces:
            yield E_REF(
                f"'{obj.id}' is drawn in space '{drawn_in}', which is not in spaces",
                path=f"{path}.in",
                objects=[obj.id],
                hint=_did_you_mean(drawn_in, spaces) or f"spaces: {', '.join(spaces) or 'none'}",
            )
        target = getattr(obj, "next_to", None)
        if target == obj.id:
            yield E_REF(
                f"'{obj.id}' is next to '{target}', which is itself",
                path=f"{path}.next_to",
                objects=[obj.id],
            )
        elif target is not None and target not in points:
            yield E_REF(
                f"'{obj.id}' is next to '{target}', which is not an object or zone",
                path=f"{path}.next_to",
                objects=[obj.id],
                hint=_did_you_mean(target, [p for p in points if p not in RESERVED]),
            )
        label = getattr(obj, "label", None)
        if label is not None and label.at not in points[obj.id]:
            yield E_REF(
                f"the label of '{obj.id}' sits at '{label.at}', which {obj.type} has not",
                path=f"{path}.label.at",
                objects=[obj.id],
                hint=_did_you_mean(label.at, points[obj.id])
                or f"its points: {', '.join(points[obj.id])}",
            )


def _reference(
    ref: str | OnRef,
    path: str,
    owner: str | None,
    points: dict[str, tuple[str, ...]],
    outlined: set[str],
) -> Iterator[Issue]:
    objects = [owner] if owner else []
    if isinstance(ref, OnRef):
        if ref.on not in outlined:
            yield E_REF(
                f'{{"on": "{ref.on}"}} needs a shape to follow, and \'{ref.on}\' is '
                + ("not one" if ref.on in points else "not an object"),
                path=f"{path}.on",
                objects=objects,
                hint=_did_you_mean(ref.on, outlined) or "a point on an outline needs a shape",
            )
        return
    target, name = split_ref(ref)
    if target not in points:
        yield E_REF(
            f"'{ref}' refers to '{target}', which is not an object, zone, frame or safe",
            path=path,
            objects=objects,
            hint=_did_you_mean(target, points),
        )
    elif name not in points[target]:
        if name in BASELINE_ANCHORS:
            bottom = name.replace("baseline", "bottom")
            hint = f"only texts, formulas and stacks have a baseline; '{bottom}' is the box's"
        else:
            hint = _did_you_mean(name, points[target]) or f"its points: {', '.join(points[target])}"
        yield E_REF(f"'{target}' has no point '{name}'", path=path, objects=objects, hint=hint)


def _did_you_mean(word: str, candidates: Collection[str]) -> str | None:
    close = difflib.get_close_matches(word, list(candidates), n=1)
    return f"did you mean '{close[0]}'?" if close else None
