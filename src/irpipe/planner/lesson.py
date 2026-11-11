"""A whole lesson: the planner plans it, the agent draws each frame, and a frame that does
not fit goes back to the planner (analysis §1, the way back to the planner).

    result = run_lesson("vector projection", Path("lessons/projection"))
    result.ready, result.frames, result.returns, result.cost_usd

1. The planner plans the lesson into the folder (session.py).
2. The agent draws each frame, in the lesson's order, into ``runs/<frame id>/``.
3. A frame whose run goes to the planner goes back to it: with the agent's
   request (E-REPLAN: shorten the brief, or split the frame), or else with
   a ``fix`` request that lists the open issues (E-BRIEF). The planner
   changes the lesson; the run folder is kept as ``runs/<frame id>.<n>``,
   and every frame whose brief changed (or that the split made) is drawn
   again. A frame, with the frames split from it, goes back at most
   ``max_returns`` times; after that it stays as it is, for a person to see.
4. A run that goes to a person (a missing tool, a compiler fault) stops the
   lesson: the frames after it would stop the same way.
5. ``lesson.json`` sums it up: each frame's status, turns, returns and cost,
   every return, and the cost of the whole lesson.
"""

import json
import shutil
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Final

from irpipe.agent import AgentError, LLMClient, run_agent
from irpipe.agent.sandbox import Sandbox
from irpipe.core import Issue, load_config
from irpipe.orchestrator.inputs import LESSON_FILE
from irpipe.orchestrator.routing import Destination
from irpipe.planner.answer import brief_file
from irpipe.planner.session import PlannerError, plan, revise
from irpipe.planner.settings import PlannerSettings
from irpipe.planner.wishes import Wishes
from irpipe.schema.brief import LessonPlan
from irpipe.schema.request import PlannerRequest

RUNS: Final = "runs"
SUMMARY: Final = "lesson.json"
NO_PICTURE: Final = "NO_PICTURE"
NOT_DRAWN: Final = "NOT_DRAWN"


@dataclass(frozen=True)
class FrameRun:
    frame: str
    status: str
    """The report's status (READY, NOT_READY, STOPPED); NO_PICTURE or NOT_DRAWN."""
    next: str
    """Who acts next, in words."""
    turns: int = 0
    returns: int = 0
    """Times this frame, or the frame it was split from, went back to the planner."""
    cost_usd: float = 0.0
    folder: str | None = None


@dataclass(frozen=True)
class Return:
    frame: str
    kind: str
    reason: str
    became: tuple[str, ...]
    """The frames drawn in its place: itself, or the two split from it."""


@dataclass
class LessonResult:
    folder: Path
    lesson: LessonPlan
    frames: list[FrameRun]
    returns: list[Return] = field(default_factory=list)
    cost_usd: float = 0.0
    ended: str = ""

    @property
    def ready(self) -> bool:
        return all(frame.status == "READY" for frame in self.frames)


def run_lesson(
    topic: str,
    folder: Path,
    *,
    wishes: Wishes | None = None,
    config_path: Path = Path("pipeline.toml"),
    planner_client: LLMClient | None = None,
    agent_client: LLMClient | None = None,
    sandbox: Sandbox | None = None,
) -> LessonResult:
    """Plan a lesson on ``topic`` into ``folder`` and draw every frame of it."""
    wishes = wishes or Wishes()
    settings = PlannerSettings.from_config(load_config(config_path))
    runs = folder / RUNS
    shutil.rmtree(runs, ignore_errors=True)
    (folder / SUMMARY).unlink(missing_ok=True)
    planned = plan(topic, folder, wishes=wishes, config_path=config_path, client=planner_client)
    lesson, cost = planned.lesson, planned.cost_usd
    order = [outline.id for outline in lesson.frames]
    done: dict[str, FrameRun] = {}
    returns: dict[str, int] = {}
    back: list[Return] = []
    ended = ""
    while (frame := next((f for f in order if f not in done), None)) is not None:
        run = runs / frame
        try:
            result = run_agent(
                folder / brief_file(frame), run, lesson_path=folder / LESSON_FILE,
                config_path=config_path, client=agent_client, sandbox=sandbox,
            )  # fmt: skip
        except AgentError as error:
            said = f"the agent made no picture: {error}"
            done[frame] = FrameRun(frame, NO_PICTURE, said, returns=returns.get(frame, 0))
            continue
        cost += result.cost_usd
        route, said = result.outcome.route, result.outcome.route.describe()
        if route.to is Destination.PLANNER and returns.get(frame, 0) < settings.max_returns:
            request = result.request or fix_request(frame, route.issues)
            try:
                revised = revise(
                    request, folder, wishes=wishes, config_path=config_path, client=planner_client
                )
            except PlannerError as error:
                said += f"; the planner could not change its brief: {error}"
            else:
                cost += revised.cost_usd
                now = [outline.id for outline in revised.lesson.frames]
                became = tuple(f for f in now if f not in order) or (frame,)
                for name in became:
                    returns[name] = returns.get(frame, 0) + 1
                back.append(Return(frame, request.kind, request.reason, became))
                _keep(run)
                for name in (*revised.changed, *(f for f in order if f not in now)):
                    done.pop(name, None)
                lesson, order = revised.lesson, now
                continue
        done[frame] = FrameRun(
            frame, str(result.outcome.report.status), said, len(result.turns),
            returns.get(frame, 0), round(result.cost_usd, 6), str(run.relative_to(folder)),
        )  # fmt: skip
        if route.to is Destination.HUMAN:
            ended = f"frame {frame!r} needs a person ({route.describe()}); the lesson stopped"
            break
    frames = [
        done.get(f) or FrameRun(f, NOT_DRAWN, "not drawn: the lesson stopped first") for f in order
    ]
    if not ended:
        ready = sum(f.status == "READY" for f in frames)
        ended = f"{ready} of {len(frames)} frames are READY"
    summary = LessonResult(folder, lesson, frames, back, round(cost, 6), ended)
    _summary(summary, topic)
    return summary


def fix_request(frame: str, issues: Sequence[Issue]) -> PlannerRequest:
    """The open issues that sent a frame to the planner, as a ``fix`` request."""
    lines = tuple(
        f"{i.code}: {i.message}" + (f" (at {i.path})" if i.path else "")
        + (f"; hint: {i.hint}" if i.hint else "")
        for i in issues
    )  # fmt: skip
    reason = "the pipeline cannot draw the frame from its brief and lesson plan as they are"
    return PlannerRequest(frame=frame, kind="fix", reason=reason, issues=lines)


def _keep(run: Path) -> None:
    """A run folder whose frame went back to the planner, kept as ``<frame>.<n>``."""
    if not run.exists():
        return
    number = 1
    while (kept := run.with_name(f"{run.name}.{number}")).exists():
        number += 1
    run.rename(kept)


def _summary(result: LessonResult, topic: str) -> None:
    data = {
        "topic": topic,
        "lesson": result.lesson.id,
        "ready": result.ready,
        "ended": result.ended,
        "frames": [asdict(frame) for frame in result.frames],
        "returns": [asdict(back) for back in result.returns],
        "cost_usd": result.cost_usd,
    }
    text = json.dumps(data, indent=2, ensure_ascii=False)
    (result.folder / SUMMARY).write_text(text + "\n", encoding="utf-8")
