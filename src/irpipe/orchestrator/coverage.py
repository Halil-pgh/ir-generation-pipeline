"""Does the picture show what the brief says it must? (analysis §2.7, static coverage)

    issues = coverage_issues(brief, document)

An object says which of the brief's ``must_show`` items it shows with
``"covers": ["shadow"]``. Every item must be covered by at least one drawn
object (defs are not drawn): an item no object covers is W-UNCOVERED, which
the agent fixes or, if the item is shown after all, accepts with ``allow``.
A ``covers`` that names no item of the brief is an E-REF.
"""

import difflib

from irpipe.core import ISSUE_CODES, Issue, IssueCode, Origin
from irpipe.frontend.references import E_REF, body_objects
from irpipe.schema.brief import FrameBrief
from irpipe.schema.ir import IRDocument

W_UNCOVERED = ISSUE_CODES.register(
    IssueCode(
        "W-UNCOVERED",
        Origin.IR,
        "an item the brief says the picture must show is covered by no object",
        allowable=True,
    )
)


def coverage_issues(brief: FrameBrief, document: IRDocument) -> list[Issue]:
    """W-UNCOVERED for each must_show item no object covers; E-REF for a covers of nothing."""
    items = [item.id for item in brief.must_show]
    issues: list[Issue] = []
    covered: set[str] = set()
    for path, obj in body_objects(document):
        if path.startswith("defs"):
            continue
        for k, name in enumerate(obj.covers):
            if name in items:
                covered.add(name)
                continue
            close = difflib.get_close_matches(name, items, n=1)
            issues.append(
                E_REF(
                    f"'{obj.id}' covers '{name}', which is not in the brief's must_show",
                    path=f"{path}.covers[{k}]",
                    objects=[obj.id],
                    hint=f"did you mean '{close[0]}'?"
                    if close
                    else f"must_show: {', '.join(items)}",
                )
            )
    for item in brief.must_show:
        if item.id not in covered:
            issues.append(
                W_UNCOVERED(
                    f"must_show '{item.id}' ({item.text}) is covered by no object",
                    hint=f'add "covers": ["{item.id}"] to the object that shows it',
                )
            )
    return issues
