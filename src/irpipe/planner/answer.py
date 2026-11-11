"""The planner's answer: the JSON in it, the files it makes, and what is wrong with them.

    data, problems = extract(reply_text)               # {"lesson_plan": ..., "briefs": [...]}
    draft, problems = write_draft(data, folder, kept, wishes)
    lesson, briefs, problems = read_draft(draft)        # the orchestrator's own reading
    problems += plan_problems(lesson, briefs, draft, settings=..., wishes=...)

An answer is one JSON object, ``{"lesson_plan": {...}, "briefs": [{...}]}``,
alone or in a Markdown fence. Its files are written as the lesson folder
holds them (lesson_plan.json, and ``<frame id>.brief.json`` beside it) into
a folder of their own, the draft, with the user's wishes laid over them;
then every brief is read as the orchestrator reads it (``read_inputs``:
its schema, its lesson, its style, the header it makes), so a brief the
planner hands on can be drawn. What no schema says is checked here: every
frame of the lesson has a brief, with the frame's purpose; the number of
frames; and, for a revision, that the answer does what was asked.

A problem is one line, said so that the model can fix it.
"""

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from irpipe.orchestrator.inputs import LESSON_FILE, read_inputs
from irpipe.planner.settings import PlannerSettings
from irpipe.planner.wishes import Wishes
from irpipe.schema.brief import FrameBrief, LessonPlan
from irpipe.schema.color import NAME_PATTERN
from irpipe.schema.request import PlannerRequest

KEYS = ("lesson_plan", "briefs")
BRIEF_SUFFIX = ".brief.json"
FENCE = re.compile(r"```[a-zA-Z]*[ \t]*\n(.*?)\n[ \t]*```", re.DOTALL)


def brief_file(frame_id: str) -> str:
    """The name of a frame's brief in the lesson folder."""
    return frame_id + BRIEF_SUFFIX


def briefs_in(folder: Path) -> dict[str, Path]:
    """Frame id -> brief file, for every brief in ``folder``."""
    return {p.name.removesuffix(BRIEF_SUFFIX): p for p in sorted(folder.glob("*" + BRIEF_SUFFIX))}


def extract(text: str) -> tuple[dict[str, Any] | None, list[str]]:
    """The answer's JSON object, from a fence (the longest) or from its first ``{`` to its
    last ``}``; or what is wrong with it."""
    fenced = [m.group(1) for m in FENCE.finditer(text)]
    if fenced:
        body = max(fenced, key=len)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < start:
            return None, ['the answer holds no JSON object: answer with {"lesson_plan": ...}']
        body = text[start : end + 1]
    try:
        data = json.loads(body)
    except json.JSONDecodeError as error:
        where = f"line {error.lineno}, column {error.colno}"
        return None, [f"the answer is not valid JSON: {error.msg} ({where} of the object)"]
    if not isinstance(data, dict):
        return None, ["the answer is JSON, but not an object with lesson_plan and briefs"]
    problems = [f"the answer has no {key!r}" for key in KEYS if key not in data]
    problems += [
        f"the answer holds {key!r}; it holds only lesson_plan and briefs"
        for key in data
        if key not in KEYS
    ]
    if "lesson_plan" in data and not isinstance(data["lesson_plan"], dict):
        problems.append("lesson_plan is a JSON object")
    briefs = data.get("briefs")
    if "briefs" in data and not (
        isinstance(briefs, list) and all(isinstance(b, dict) for b in briefs)
    ):
        problems.append("briefs is a list of JSON objects, one brief each")
    return (None, problems) if problems else (data, [])


@dataclass(frozen=True)
class Draft:
    folder: Path
    lesson_path: Path
    briefs: dict[str, Path]
    """Frame id -> brief file: the answer's briefs, and the kept ones of the lesson's frames."""
    answered: tuple[str, ...]
    """The frames whose brief the answer wrote, in its order."""


def write_draft(
    data: dict[str, Any], folder: Path, kept: dict[str, Path], wishes: Wishes
) -> tuple[Draft, list[str]]:
    """The answer's files in ``folder``, with the wishes laid over them; the earlier briefs
    (``kept``) of frames the lesson still has and the answer did not write, copied beside."""
    folder.mkdir(parents=True, exist_ok=True)
    lesson = wishes.lay_over_lesson(data["lesson_plan"])
    lesson_path = folder / LESSON_FILE
    lesson_path.write_text(_json(lesson), encoding="utf-8")
    problems: list[str] = []
    briefs: dict[str, Path] = {}
    for number, raw in enumerate(data["briefs"], start=1):
        frame_id = raw.get("id")
        if not (isinstance(frame_id, str) and re.fullmatch(NAME_PATTERN, frame_id)):
            problems.append(
                f"briefs[{number - 1}] has the id {json.dumps(frame_id)}: a brief's id is its "
                "frame's id, a letter, then letters, digits or _"
            )
            continue
        if frame_id in briefs:
            problems.append(f"two briefs have the id {frame_id!r}: one brief per frame")
            continue
        briefs[frame_id] = folder / brief_file(frame_id)
        briefs[frame_id].write_text(_json(wishes.lay_over_brief(raw)), encoding="utf-8")
    answered = tuple(briefs)
    frames = _frame_ids(lesson)
    for frame_id, path in kept.items():
        if frame_id not in briefs and frame_id in frames:
            briefs[frame_id] = Path(shutil.copy2(path, folder / brief_file(frame_id)))
    return Draft(folder, lesson_path, briefs, answered), problems


def read_draft(draft: Draft) -> tuple[LessonPlan | None, dict[str, FrameBrief], list[str]]:
    """The lesson and every brief, read as the orchestrator reads them; or their problems."""
    problems: list[str] = []
    briefs: dict[str, FrameBrief] = {}
    for frame_id, path in draft.briefs.items():
        inputs, issues = read_inputs(path, draft.lesson_path)
        for issue in issues:
            line = issue.message + (f" (at {issue.path})" if issue.path else "")
            line += f"; hint: {issue.hint}" if issue.hint else ""
            if line not in problems:  # a broken lesson plan is said once, not once a brief
                problems.append(line)
        if inputs is not None:
            briefs[frame_id] = inputs.brief
    if not draft.briefs:
        problems.append("the answer holds no brief")
    try:
        text = draft.lesson_path.read_text(encoding="utf-8")
        lesson = LessonPlan.model_validate_json(text, strict=True)
    except ValidationError:
        lesson = None  # its problems came with the briefs'
    return lesson, briefs, problems


def plan_problems(
    lesson: LessonPlan,
    briefs: dict[str, FrameBrief],
    draft: Draft,
    *,
    settings: PlannerSettings,
    wishes: Wishes,
    request: PlannerRequest | None = None,
    before: LessonPlan | None = None,
) -> list[str]:
    """What no schema checks: a brief for every frame, with its purpose; the number of
    frames; and that a revision does what ``request`` asked of the lesson ``before``.
    ``briefs`` are the briefs of ``draft`` that could be read."""
    problems = []
    for outline in lesson.frames:
        brief = briefs.get(outline.id)
        if outline.id not in draft.briefs:
            problems.append(f"frame {outline.id!r} of the lesson plan has no brief")
        elif brief is not None and brief.purpose != outline.purpose:
            problems.append(
                f"brief {outline.id!r} has the purpose {brief.purpose!r}, but the lesson plan "
                f"gives frame {outline.id!r} the purpose {outline.purpose!r}: make them the same"
            )
    count = len(lesson.frames)
    if count > settings.max_frames:
        problems.append(f"the lesson has {count} frames; it may have at most {settings.max_frames}")
    if request is None:
        if wishes.frames is not None and count != wishes.frames:
            problems.append(
                f"the user asks for exactly {wishes.frames} frames; the lesson has {count}"
            )
        return problems
    if before is None:
        raise ValueError("a revision is checked against the lesson plan before it")
    if lesson.id != before.id:
        problems.append(f"keep the lesson's id {before.id!r}")
    return problems + _revision_problems(lesson, set(draft.answered), request, before)


def _revision_problems(
    lesson: LessonPlan, answered: set[str], request: PlannerRequest, before: LessonPlan
) -> list[str]:
    frame = request.frame
    now = [f.id for f in lesson.frames]
    then = [f.id for f in before.frames]
    if request.kind != "split":
        if frame not in now:
            return [f"keep frame {frame!r} under its id: change its brief, do not replace it"]
        if request.kind == "shorten" and now != then:
            return [f"keep the lesson's frames as they are ({', '.join(then)}): only the brief "
                    f"of {frame!r} changes"]  # fmt: skip
        if frame not in answered:
            return [f"the answer holds no brief for frame {frame!r}: write its new brief"]
        return []
    if frame in now:
        return [f"frame {frame!r} is split: the lesson plan no longer lists it, but the two "
                "frames that take its place, under new ids"]  # fmt: skip
    place = then.index(frame)
    head, tail = then[:place], then[place + 1 :]
    middle = now[len(head) : len(now) - len(tail)]
    kept_order = now[: len(head)] == head and now[len(now) - len(tail) :] == tail
    if not kept_order or len(middle) < 2 or set(middle) & set(then):
        order = ", ".join([*head, "<new frame>", "<new frame>", *tail])
        return [f"put two new frames (new ids) where {frame!r} was, the others as they were: "
                f"{order}"]  # fmt: skip
    return []  # a new frame without a brief is said by plan_problems


def _frame_ids(lesson: Any) -> set[str]:
    frames = lesson.get("frames") if isinstance(lesson, dict) else None
    if not isinstance(frames, list):
        return set()
    return {f["id"] for f in frames if isinstance(f, dict) and isinstance(f.get("id"), str)}


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
