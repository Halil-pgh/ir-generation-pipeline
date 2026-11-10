"""Turns JSON and pydantic errors into issues the agent can act on.

A raw pydantic error reads ``objects.3.circle.raduis: Extra inputs are not
permitted``. The agent gets ``E-SCHEMA objects[3].raduis: unknown field
'raduis'`` with the hint ``did you mean 'radius'?``: a JSON path into its own
file, in plain words.

When a value fits none of the forms a field allows (a color that is neither
``"#RRGGBB"`` nor ``[r, g, b]``), pydantic reports one error per form; they
are folded into one issue that says which forms are allowed.
"""

import difflib
import json
from collections.abc import Collection, Sequence
from typing import Any

from pydantic import ValidationError
from pydantic_core import ErrorDetails

from irpipe.core import ISSUE_CODES, Issue, IssueCode, Origin
from irpipe.frontend.expressions import E_EXPR

E_JSON = ISSUE_CODES.register(IssueCode("E-JSON", Origin.IR, "the IR cannot be read as JSON"))
E_SCHEMA = ISSUE_CODES.register(
    IssueCode(
        "E-SCHEMA", Origin.IR, "a field is unknown, missing, or has a value of the wrong form"
    )
)

COLOR_FORMS = 'a color is "#RRGGBB", [r, g, b], the name of a color, or "none"'
POINT_FORMS = (
    'a point is [x, y], a reference "id.anchor" (such as "v.tip" or "safe.center_top"), '
    'or {"on": id, "t": 0..1} or {"on": id, "x": x}'
)
FORM_HINTS = {
    "color": COLOR_FORMS,
    "fill": COLOR_FORMS,
    "background": 'a color is "#RRGGBB" or [r, g, b]',
    "size": "a text role (title, heading, body, label, caption) or a size in reference px",
    "style": "a style class name, or a list of them",
    "scale": "one factor, or [sx, sy]",
    "segments": 'a segment is {"line": p}, {"quad": [c, p]} or {"cubic": [c1, c2, p]}',
    "dir": "a direction is up, down, left, right, up_left, up_right, down_left, down_right, "
    "an angle in degrees, or [dx, dy]",
    "spacing": "one number, or [between columns, between rows]",
    "unit": "one number, or [ux, uy]",
    **dict.fromkeys(("center", "at", "start", "end", "points", "pivot", "origin"), POINT_FORMS),
}
"""What to tell the agent when a value fits none of a field's forms, by field name."""

type Path = list[str | int]


def parse_json(text: str) -> tuple[Any, list[Issue]]:
    """The parsed JSON, or an E-JSON issue that says where reading stopped."""
    try:
        return json.loads(text), []
    except json.JSONDecodeError as exc:
        issue = E_JSON(
            f"{exc.msg} at line {exc.lineno}, column {exc.colno}",
            hint="look for a missing comma, quote or bracket just before that point; "
            "JSON allows no comments",
        )
        return None, [issue]


def schema_issues(raw: Any, error: ValidationError, field_names: Collection[str]) -> list[Issue]:
    """One issue per place in the file where the IR breaks the schema.

    A failed expression is E-EXPR, even where the field also allows another
    form; everything else is E-SCHEMA.
    """
    located = [(locate(raw, detail["loc"]), detail) for detail in error.errors()]
    places: dict[str, tuple[Path, list[ErrorDetails]]] = {}
    for path, detail in located:
        if detail["type"] == "too_short" and _deeper_error(path, located):
            continue  # a list counted short only because its items failed; the items say why
        places.setdefault(format_path(path), (path, []))[1].append(detail)
    issues = []
    for where, (path, details) in places.items():
        expression = next((d for d in details if d["type"] == "expression"), None)
        if expression is not None:
            context = expression.get("ctx") or {}
            hint = str(context.get("hint", "")) or None
            exact = format_path(locate(raw, expression["loc"], through_unions=True))
            issues.append(E_EXPR(str(context.get("message")), path=exact or None, hint=hint))
            continue
        if len(details) == 1:
            message, hint = describe(details[0], field_names)
        else:
            message = f"{_shown(value_at(raw, path))} fits none of the allowed forms"
            field = next((p for p in reversed(path) if isinstance(p, str)), "")
            hint = FORM_HINTS.get(field) or "; ".join(dict.fromkeys(d["msg"] for d in details))
        issues.append(E_SCHEMA(message, path=where or None, hint=hint))
    return issues


def locate(raw: Any, loc: Sequence[str | int], *, through_unions: bool = False) -> Path:
    """The part of a pydantic location that is a path in the file.

    Pydantic locations also name the union member they tried (``circle``,
    ``tuple[...]``). The tag of a typed object is skipped; at the first other
    union member the path stops, so every member's error lands in one place.
    ``through_unions`` skips the member's name instead and follows the path
    to the end: an expression's error belongs to the number it is in
    (``center[1]``), whatever other forms the point could have taken.
    """
    path: Path = []
    node = raw
    tag_skipped = False
    for i, part in enumerate(loc):
        if isinstance(node, dict) and node.get("type") == part and not tag_skipped:
            # The "type" tag that picked the model, not a field (a text has a "text" field too).
            tag_skipped = True
            continue
        if _holds(node, part):
            path.append(part)
            node = node[part]
            tag_skipped = False
        elif isinstance(part, str) and isinstance(node, dict) and i == len(loc) - 1:
            path.append(part)  # a field that is missing from the file
        elif through_unions and isinstance(part, str):
            continue  # the name of the form that was tried
        else:
            break  # one of several forms the value could have taken
    return path


def _deeper_error(path: Path, located: list[tuple[Path, ErrorDetails]]) -> bool:
    return any(len(other) > len(path) and other[: len(path)] == path for other, _ in located)


def _holds(node: Any, part: str | int) -> bool:
    """Is ``part`` an index or key that exists in ``node``?"""
    if isinstance(part, int):
        return isinstance(node, list) and 0 <= part < len(node)
    return isinstance(node, dict) and part in node


def format_path(path: Path) -> str:
    """``["objects", 3, "radius"]`` -> ``objects[3].radius``."""
    text = ""
    for part in path:
        text += f"[{part}]" if isinstance(part, int) else (f".{part}" if text else part)
    return text


def value_at(raw: Any, path: Path) -> Any:
    node = raw
    for part in path:
        node = node[part]
    return node


def describe(detail: ErrorDetails, field_names: Collection[str]) -> tuple[str, str | None]:
    """A message and a hint for one pydantic error."""
    kind, key = detail["type"], detail["loc"][-1] if detail["loc"] else ""
    context = detail.get("ctx") or {}
    if kind == "missing":
        return f"missing field '{key}'", None
    if kind == "extra_forbidden":
        return f"unknown field '{key}'", _did_you_mean(str(key), field_names)
    if kind == "union_tag_invalid":
        tag = str(context.get("tag", ""))
        known = [t.strip(" '") for t in str(context.get("expected_tags", "")).split(",")]
        hint = _did_you_mean(tag, known) or f"known types: {', '.join(known)}"
        return f"unknown type '{tag}'", hint
    if kind == "value_error" and "error" in context:
        return str(context["error"]), None  # a rule a model checks itself; drop "Value error, "
    if kind == "too_short":
        least = context.get("min_length", 1)
        return f"needs at least {least} item{'' if least == 1 else 's'}", None
    if kind == "union_tag_not_found":
        return "missing field 'type'", 'every object says what it is, such as "type": "circle"'
    if kind in {"model_type", "dict_type"} and not detail["loc"]:
        return "ir.json must hold one JSON object", None
    return detail["msg"], None


def _did_you_mean(word: str, candidates: Collection[str]) -> str | None:
    close = difflib.get_close_matches(word, candidates, n=1)
    return f"did you mean '{close[0]}'?" if close else None


def _shown(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= 40 else text[:37] + "..."
