"""Checks that every name in the IR points at something, and that groups nest properly.

The schema has already checked the form of every field; this module checks
what the names mean:

- E-ID: two objects, defs or spaces share an id.
- E-REF: a name points at nothing: an object in ``focus`` or in a group, a
  style class, or a color.
- E-GROUP: groups are put together wrongly: an object in two groups, a
  group that contains itself, or a def (which is never drawn) in a group.
"""

import difflib
from collections.abc import Collection, Iterator

from irpipe.core import ISSUE_CODES, Issue, IssueCode, Origin
from irpipe.schema.color import NO_PAINT
from irpipe.schema.ir import Group, IRDocument
from irpipe.schema.ir.objects import ObjectBase

E_ID = ISSUE_CODES.register(IssueCode("E-ID", Origin.IR, "two things in the IR share an id"))
E_REF = ISSUE_CODES.register(
    IssueCode("E-REF", Origin.IR, "a name points at nothing: no such object, style or color")
)
E_GROUP = ISSUE_CODES.register(
    IssueCode(
        "E-GROUP", Origin.IR, "a group is built wrongly: shared child, a loop, or a def inside"
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
    return issues


def body_objects(document: IRDocument) -> Iterator[tuple[str, ObjectBase]]:
    """Every object and def with its JSON path."""
    for k, obj in enumerate(document.defs):
        yield f"defs[{k}]", obj
    for k, obj in enumerate(document.objects):
        yield f"objects[{k}]", obj


def _duplicate_ids(document: IRDocument) -> Iterator[Issue]:
    first: dict[str, str] = {}
    named = [(f"spaces[{k}]", space.id) for k, space in enumerate(document.spaces)]
    named += [(path, obj.id) for path, obj in body_objects(document)]
    for path, oid in named:
        if oid in first:
            yield E_ID(
                f"id '{oid}' is already used by {first[oid]}",
                path=f"{path}.id",
                objects=[oid],
                hint="give every object, def and space its own id",
            )
        else:
            first[oid] = path


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
    for k, group in enumerate(document.objects):
        if not isinstance(group, Group):
            continue
        gid, seen = group.id, set[str]()
        for j, child in enumerate(group.children):
            where = f"objects[{k}].children[{j}]"
            if child == gid:
                yield E_GROUP(f"group '{gid}' lists itself", path=where, objects=[gid])
            elif child in seen:
                yield E_GROUP(
                    f"group '{gid}' lists '{child}' twice", path=where, objects=[gid, child]
                )
            elif child in defs:
                yield E_GROUP(
                    f"group '{gid}' lists def '{child}'; defs are never drawn",
                    path=where,
                    objects=[gid, child],
                    hint="move the object from defs to objects, or leave it out of the group",
                )
            elif child not in objects:
                yield E_REF(
                    f"group '{gid}' lists '{child}', which is not an object",
                    path=where,
                    objects=[gid],
                    hint=_did_you_mean(child, objects),
                )
            elif child in parent:
                yield E_GROUP(
                    f"'{child}' is already in group '{parent[child]}'; "
                    "an object belongs to at most one group",
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
            "groups contain each other: " + " -> ".join([*reversed(loop), loop[-1]]),
            path=paths[loop[-1]],
            objects=loop,
            hint="a group may not end up inside itself",
        )


def _did_you_mean(word: str, candidates: Collection[str]) -> str | None:
    close = difflib.get_close_matches(word, list(candidates), n=1)
    return f"did you mean '{close[0]}'?" if close else None
