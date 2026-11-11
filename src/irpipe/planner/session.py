"""The planner at work: a lesson from a topic, and a frame's brief changed when it comes back.

    result = plan("vector projection", Path("lessons/projection"), wishes=Wishes(frames=3))
    result.lesson, result.briefs            # lesson_plan.json, <frame id>.brief.json
    result = revise(request, Path("lessons/projection"))   # shorten, split or fix one frame

The model answers with the lesson plan and the briefs (answer.py). Each
answer is written as a draft into ``planner/answers/<n>/`` and checked: as
the orchestrator reads it, and for what no schema says. An answer with
problems is sent back with them, within ``max_answers`` answers; the first
one without is copied into the lesson folder. A revision keeps the briefs
the answer leaves out, and removes the brief of a frame that was split.

The lesson folder:

    lesson_plan.json, <frame id>.brief.json   what the agent draws from
    planner/system_prompt.md                  the system prompt
    planner/transcript.md                     every message, of every session
    planner/answers/<n>/                      each answer: answer.md and its draft files
    planner/session.json                      settings, wishes, and each session: what it
                                              was asked, its answers, problems and cost
"""

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from irpipe.agent.llm import LLM_CLIENTS, LLMClient, LLMError, Message
from irpipe.core import load_config
from irpipe.orchestrator.inputs import LESSON_FILE
from irpipe.planner.answer import (
    Draft,
    brief_file,
    briefs_in,
    extract,
    plan_problems,
    read_draft,
    write_draft,
)
from irpipe.planner.prompt import (
    plan_message,
    problems_message,
    read_example,
    revise_message,
    system_prompt,
)
from irpipe.planner.settings import PlannerSettings
from irpipe.planner.wishes import Wishes
from irpipe.schema.brief import LessonPlan
from irpipe.schema.request import PlannerRequest

PLANNER = "planner"


class PlannerError(RuntimeError):
    """The planner made no usable lesson: the model could not answer, or every answer had
    problems (planner/ keeps them)."""


@dataclass(frozen=True)
class PlanResult:
    folder: Path
    lesson: LessonPlan
    briefs: dict[str, Path]
    """Frame id -> its brief in the lesson folder, in the lesson's order."""
    changed: tuple[str, ...]
    """The frames whose brief this session wrote."""
    answers: int
    cost_usd: float


def plan(
    topic: str,
    folder: Path,
    *,
    wishes: Wishes | None = None,
    config_path: Path = Path("pipeline.toml"),
    client: LLMClient | None = None,
) -> PlanResult:
    """Plan a lesson on ``topic`` into ``folder``: its lesson plan and a brief per frame.

    An earlier lesson in ``folder`` (its plan, briefs and planner records) is replaced.
    """
    wishes = wishes or Wishes()
    folder.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(folder / PLANNER, ignore_errors=True)
    (folder / LESSON_FILE).unlink(missing_ok=True)
    for path in briefs_in(folder).values():
        path.unlink()
    planner = _Planner(folder, config_path, client, wishes)
    asked = {"kind": "plan", "topic": topic}
    return planner.session(asked, plan_message(topic, wishes), None, None)


def revise(
    request: PlannerRequest,
    folder: Path,
    *,
    wishes: Wishes | None = None,
    config_path: Path = Path("pipeline.toml"),
    client: LLMClient | None = None,
) -> PlanResult:
    """Change the lesson in ``folder`` as ``request`` asks: shorten, split or fix one frame."""
    wishes = wishes or Wishes()
    lesson_path, brief_path = folder / LESSON_FILE, folder / brief_file(request.frame)
    if not (lesson_path.exists() and brief_path.exists()):
        raise PlannerError(f"{folder} holds no lesson with a frame {request.frame!r}")
    lesson_text = lesson_path.read_text(encoding="utf-8")
    before = LessonPlan.model_validate_json(lesson_text, strict=True)
    brief_text = brief_path.read_text(encoding="utf-8")
    planner = _Planner(folder, config_path, client, wishes)
    first = revise_message(request, lesson_text, brief_text, wishes)
    asked = {"kind": request.kind, "request": request.model_dump()}
    return planner.session(asked, first, request, before)


class _Planner:
    def __init__(
        self, folder: Path, config_path: Path, client: LLMClient | None, wishes: Wishes
    ) -> None:
        config = load_config(config_path)
        self.settings = PlannerSettings.from_config(config)
        self.client = client or LLM_CLIENTS.get(self.settings.provider)(
            self.settings.client_settings()
        )
        self.folder = folder
        self.wishes = wishes
        self.records = folder / PLANNER
        self.records.mkdir(exist_ok=True)
        example = None
        if self.settings.example:
            where = Path(self.settings.example)
            example = read_example(where if where.is_absolute() else config_path.parent / where)
        self.system = system_prompt(self.settings, example)
        (self.records / "system_prompt.md").write_text(self.system, encoding="utf-8")

    def session(
        self,
        asked: dict[str, Any],
        first: str,
        request: PlannerRequest | None,
        before: LessonPlan | None,
    ) -> PlanResult:
        """Ask, check each answer and send its problems back, until one can be used."""
        kept = briefs_in(self.folder)
        messages = [Message("user", first)]
        self._log("user", first)
        record: dict[str, Any] = {**asked, "answers": [], "cost_usd": 0.0}
        cost = 0.0
        problems: list[str] = []
        for _ in range(self.settings.max_answers):
            try:
                reply = self.client.complete(self.system, messages)
            except LLMError as error:
                self._finish(record, cost, f"the model could not answer: {error}")
                raise PlannerError(f"the planner's model could not answer: {error}") from error
            cost += reply.cost_usd or 0.0
            self._log("assistant", reply.text)
            number = self._next_answer()
            draft, problems = self._check(reply.text, number, kept, request, before)
            record["answers"].append({"answer": number, "problems": problems})
            if draft is not None and not problems:
                self._finish(record, cost, f"answer {number} is used")
                return self._accept(draft, len(record["answers"]), cost)
            again = problems_message(problems)
            messages += [Message("assistant", reply.text), Message("user", again)]
            self._log("user", again)
        said = f"no usable answer in {self.settings.max_answers}"
        self._finish(record, cost, said)
        raise PlannerError(f"the planner gave {said}; the last one's problems: {problems[:3]}")

    def _check(
        self,
        text: str,
        number: int,
        kept: dict[str, Path],
        request: PlannerRequest | None,
        before: LessonPlan | None,
    ) -> tuple[Draft | None, list[str]]:
        folder = self.records / "answers" / str(number)
        folder.mkdir(parents=True)
        (folder / "answer.md").write_text(text, encoding="utf-8")
        data, problems = extract(text)
        if data is None:
            return None, problems
        draft, problems = write_draft(data, folder, kept, self.wishes)
        lesson, briefs, found = read_draft(draft)
        problems += found
        if lesson is not None:
            problems += plan_problems(
                lesson, briefs, draft, settings=self.settings, wishes=self.wishes,
                request=request, before=before,
            )  # fmt: skip
        return draft, problems

    def _accept(self, draft: Draft, answers: int, cost: float) -> PlanResult:
        """The draft's files into the lesson folder; briefs of frames gone are removed."""
        shutil.copy2(draft.lesson_path, self.folder / LESSON_FILE)
        text = draft.lesson_path.read_text(encoding="utf-8")
        lesson = LessonPlan.model_validate_json(text, strict=True)
        frames = [outline.id for outline in lesson.frames]
        for frame_id, path in briefs_in(self.folder).items():
            if frame_id not in frames:
                path.unlink()
        briefs = {}
        for frame_id in frames:
            briefs[frame_id] = self.folder / brief_file(frame_id)
            if frame_id in draft.answered:
                shutil.copy2(draft.briefs[frame_id], briefs[frame_id])
        return PlanResult(self.folder, lesson, briefs, draft.answered, answers, cost)

    def _next_answer(self) -> int:
        answers = self.records / "answers"
        return 1 + (sum(1 for _ in answers.iterdir()) if answers.exists() else 0)

    def _finish(self, record: dict[str, Any], cost: float, ended: str) -> None:
        """Add this session to session.json."""
        path = self.records / "session.json"
        earlier = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        sessions = [*earlier.get("sessions", []), {**record, "cost_usd": round(cost, 6),
                                                    "ended": ended}]  # fmt: skip
        data = {
            "settings": self.settings.model_dump(),
            "wishes": self.wishes.model_dump(exclude_none=True),
            "sessions": sessions,
            "cost_usd": round(sum(s["cost_usd"] for s in sessions), 6),
        }
        text = json.dumps(data, indent=2, ensure_ascii=False)
        path.write_text(text + "\n", encoding="utf-8")

    def _log(self, role: str, text: str) -> None:
        with (self.records / "transcript.md").open("a", encoding="utf-8") as out:
            out.write(f"## {role}\n\n{text}\n\n")
