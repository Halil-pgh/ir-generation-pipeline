"""Accepting a reported problem on purpose: the IR's ``allow`` entries.

Sometimes a warning describes exactly what the picture means to show, for
example the dashed projection line in a vector projection, drawn through the
label of the vector it lands on. The IR's author then adds an entry naming
the code, the objects it is about, and why:

    {"code": "W-OVERLAP", "objects": ["proj", "b.label"],
     "reason": "the projection line runs through b's label to show where it lands"}

``check_allows`` reports malformed entries as E-ALLOW. ``apply_allows`` marks
every issue an entry matches with ``allowed_because``: the issue stays in the
report, but no longer counts against READY. Only allowable codes are ever
marked, whatever the entries say, and errors are never allowable
(core/issues.py). The matching rule is written down in docs/SEMANTICS.md.
"""

from collections.abc import Callable, Collection, Iterable, Sequence

from pydantic import BaseModel, ConfigDict

from irpipe.core.issues import ISSUE_CODES, Issue, IssueCode, Origin
from irpipe.core.registry import Registry

MIN_REASON_WORDS = 4
"""An allow entry's reason needs at least this many words.

Stock answers such as "ok", "on purpose" or "this is intended" stay below it;
a reason that names what is shown, and why, gets past it.
"""

E_ALLOW = ISSUE_CODES.register(IssueCode("E-ALLOW", Origin.IR, "an `allow` entry is malformed"))


class Allow(BaseModel):
    """One entry of the IR's ``allow`` list."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    objects: tuple[str, ...] = ()
    reason: str


type Covers = Callable[[str, str], bool]
"""``covers(named, reported)``: does an object named in an entry cover one named in an issue?"""


def covers_by_name(named: str, reported: str) -> bool:
    """An id covers itself and its parts: ``v`` covers ``v`` and ``v.label``.

    The IR layer passes a wider rule once groups exist (a group covers its
    members, step 6); this one needs nothing but the names.
    """
    return reported == named or reported.startswith(named + ".")


def matches(allow: Allow, issue: Issue, covers: Covers = covers_by_name) -> bool:
    """Same code, and every object the entry names covers an object of the issue.

    An entry that names no objects only matches issues about no object in
    particular (one about the picture as a whole), never every issue of its code.
    """
    if allow.code != issue.code:
        return False
    if not allow.objects:
        return not issue.objects
    return all(
        any(covers(named, reported) for reported in issue.objects) for named in allow.objects
    )


def apply_allows(
    issues: Iterable[Issue],
    allows: Sequence[Allow],
    *,
    codes: Registry[IssueCode] = ISSUE_CODES,
    covers: Covers = covers_by_name,
) -> tuple[Issue, ...]:
    """The issues, each marked with the reason of the first entry that accepts it."""
    marked: list[Issue] = []
    for issue in issues:
        allow = None
        if issue.code in codes and codes.get(issue.code).allowable:
            allow = next((a for a in allows if matches(a, issue, covers)), None)
        if allow is not None:
            issue = issue.model_copy(update={"allowed_because": allow.reason})
        marked.append(issue)
    return tuple(marked)


def check_allows(
    allows: Sequence[Allow],
    *,
    known_ids: Collection[str] | None = None,
    codes: Registry[IssueCode] = ISSUE_CODES,
) -> list[Issue]:
    """E-ALLOW issues for every malformed entry.

    An entry is malformed when its code is unknown or cannot be allowed, its
    reason is shorter than ``MIN_REASON_WORDS`` words, or (when ``known_ids``,
    the IR's object ids, is given) it names an object that does not exist.
    """
    issues: list[Issue] = []
    allowable = [name for name in codes.names() if codes.get(name).allowable]
    for k, allow in enumerate(allows):
        where = f"allow[{k}]"
        if allow.code not in codes:
            close = codes.closest(allow.code)
            hint = f"did you mean {close}? " if close else ""
            hint += f"codes that can be allowed: {', '.join(allowable) or 'none'}"
            issues.append(
                E_ALLOW(f"{where} names unknown code {allow.code}", path=f"{where}.code", hint=hint)
            )
        elif not codes.get(allow.code).allowable:
            issues.append(
                E_ALLOW(
                    f"{allow.code} cannot be allowed; it always has to be fixed",
                    path=f"{where}.code",
                )
            )
        for j, named in enumerate(allow.objects):
            if known_ids is not None and named.split(".")[0] not in known_ids:
                issues.append(
                    E_ALLOW(f"{where} names unknown object '{named}'", path=f"{where}.objects[{j}]")
                )
        if len(allow.reason.split()) < MIN_REASON_WORDS:
            issues.append(
                E_ALLOW(
                    "the reason must say in a few words why this is intended",
                    path=f"{where}.reason",
                    hint=f"at least {MIN_REASON_WORDS} words",
                )
            )
    return issues
