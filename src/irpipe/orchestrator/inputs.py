"""Reading the planner's files: the brief, its lesson plan, and the header they make.

    inputs, issues = read_inputs(Path("brief.json"))   # lesson_plan.json beside it, if any
    inputs.brief, inputs.style, inputs.header

Everything wrong here is the planner's to fix, so it is an E-BRIEF issue
(origin infeasible: it goes back to the planner, analysis §1): a file that
is not JSON or does not fit its schema (with the JSON path and a "did you
mean", as for the IR), a brief that does not belong to its lesson, a font
pair the project does not offer, or a render profile that leaves no frame.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ValidationError

from irpipe.core import ISSUE_CODES, Issue, IssueCode, Origin
from irpipe.frontend.schema_errors import parse_json, schema_issues
from irpipe.orchestrator.header import header_for
from irpipe.schema.brief import FrameBrief, LessonPlan, Style, frame_style
from irpipe.schema.ir import IRHeader

E_BRIEF = ISSUE_CODES.register(
    IssueCode(
        "E-BRIEF",
        Origin.INFEASIBLE,
        "the planner's brief or lesson plan is wrong or cannot be drawn: back to the planner",
    )
)

FONT_PAIRS: Final = frozenset({("Inter", "latin-modern")})
"""Text font and math font pairs the project offers (installed, licensed, matching)."""

LESSON_FILE: Final = "lesson_plan.json"


@dataclass(frozen=True)
class Inputs:
    brief: FrameBrief
    lesson: LessonPlan | None
    style: Style
    header: IRHeader
    brief_text: str


def read_inputs(
    brief_path: Path, lesson_path: Path | None = None
) -> tuple[Inputs | None, list[Issue]]:
    """The brief, its lesson (``lesson_path``, else lesson_plan.json beside the brief when
    the brief names a lesson), the frame's style and the header; or the issues instead."""
    brief_text = brief_path.read_text(encoding="utf-8")
    brief, issues = _read(FrameBrief, brief_text, brief_path.name)
    if brief is None:
        return None, issues
    lesson = None
    if lesson_path is None and brief.lesson is not None:
        beside = brief_path.with_name(LESSON_FILE)
        if not beside.exists():
            hint = f"give its lesson plan (--lesson), or put {LESSON_FILE} beside the brief"
            message = (
                f"brief '{brief.id}' belongs to lesson '{brief.lesson}', whose plan is not here"
            )
            return None, [E_BRIEF(message, path="lesson", hint=hint)]
        lesson_path = beside
    if lesson_path is not None:
        lesson, issues = _read(
            LessonPlan, lesson_path.read_text(encoding="utf-8"), lesson_path.name
        )
        if lesson is None:
            return None, issues
    try:
        style = frame_style(brief, lesson)
    except ValueError as error:
        return None, [E_BRIEF(str(error))]
    fonts = style.render_profile.typography.font_pair
    if (fonts.text, fonts.math) not in FONT_PAIRS:
        offered = "; ".join(f"{text} with {math}" for text, math in sorted(FONT_PAIRS))
        message = f"the font pair {fonts.text} with {fonts.math} is not one the project offers"
        return None, [E_BRIEF(message, path="render_profile.typography.font_pair", hint=offered)]
    try:
        header = header_for(brief, style)
    except ValueError as error:
        return None, [E_BRIEF(f"the render profile makes no frame: {error}", path="render_profile")]
    return Inputs(brief, lesson, style, header, brief_text), []


def _read[M: BaseModel](model: type[M], text: str, name: str) -> tuple[M | None, list[Issue]]:
    """``text`` read as ``model``; its problems as E-BRIEF issues, the file's name in front."""
    raw, problems = parse_json(text)
    if problems:
        return None, [_as_brief(issue, name) for issue in problems]
    try:
        return model.model_validate_json(text, strict=True), []
    except ValidationError as error:
        names = _field_names(model)
        return None, [_as_brief(issue, name) for issue in schema_issues(raw, error, names)]


def _as_brief(issue: Issue, name: str) -> Issue:
    return E_BRIEF(f"{name}: {issue.message}", path=issue.path, hint=issue.hint)


def _field_names(model: type[BaseModel]) -> frozenset[str]:
    schema: dict[str, Any] = model.model_json_schema()
    names: set[str] = set()
    for node in [schema, *schema.get("$defs", {}).values()]:
        names.update(node.get("properties", {}))
    return frozenset(names)


__all__ = ["E_BRIEF", "FONT_PAIRS", "Inputs", "read_inputs"]
