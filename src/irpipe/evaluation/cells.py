"""One cell of the eval matrix: a lesson planned (and drawn) as the cell says, and its numbers.

    result = run_cell(cell, Path("evals/lessons"), Path("pipeline.toml"))
    result.frames, result.cost_usd, result.seconds

A cell gets a copy of the project's pipeline.toml with its planner and
agent models and its backend (configs.py), and runs ``irpipe lesson`` (or
``irpipe plan`` when the matrix does not draw) on its topic, with its
aspect, frame count and language as the user's wishes, into
``<out>/cells/<cell id>/``. Its numbers are read back from the records the
planner and the agent write: the planner's answers and their problems,
each frame's status, turns, messages, returns, open issue codes and cost.

A cell that fails (the planner makes no lesson, a fault) is a result with
its error, so that one cell cannot stop the others.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from irpipe.agent import LLMClient
from irpipe.agent.sandbox import Sandbox
from irpipe.evaluation.configs import worker_config
from irpipe.evaluation.matrix import Cell
from irpipe.planner import Wishes, plan, run_lesson

LESSON = "lesson"


@dataclass(frozen=True)
class FrameResult:
    frame: str
    status: str
    turns: int
    calls: int
    returns: int
    cost_usd: float
    codes: tuple[str, ...]
    """The open issues' codes."""
    picture: str | None
    """frame.png, relative to the eval folder, when there is one."""


@dataclass
class CellResult:
    cell: Cell
    planned: bool = False
    """The planner made a lesson."""
    error: str = ""
    lesson: str = ""
    planned_frames: int = 0
    answers: int = 0
    """The planner's answers to the first plan (1 when the first one was usable)."""
    problems: int = 0
    """Problems in those answers, all told."""
    frames: list[FrameResult] = field(default_factory=list)
    returns: int = 0
    planner_cost_usd: float = 0.0
    cost_usd: float = 0.0
    seconds: float = 0.0

    @property
    def ready(self) -> int:
        return sum(frame.status == "READY" for frame in self.frames)


def run_cell(
    cell: Cell,
    out: Path,
    base_config: Path,
    *,
    planner_client: LLMClient | None = None,
    agent_client: LLMClient | None = None,
    sandbox: Sandbox | None = None,
) -> CellResult:
    """Run ``cell`` into ``out/cells/<id>/``; never raises for what goes wrong in the cell."""
    started = time.perf_counter()
    folder = out / "cells" / cell.id
    result = CellResult(cell)
    try:
        changes: dict[str, Any] = {
            "planner": {"model": cell.planner}, "agent": {"model": cell.agent},
            "options": {"render": {"backend": cell.backend}},
        }  # fmt: skip
        config = worker_config(base_config, folder, out / ".cache", changes)
        wishes = Wishes(frames=cell.frames, aspect=cell.aspect, lang=cell.lang)
        lesson_folder = folder / LESSON
        if cell.draw:
            lesson = run_lesson(
                cell.topic, lesson_folder, wishes=wishes, config_path=config,
                planner_client=planner_client, agent_client=agent_client, sandbox=sandbox,
            )  # fmt: skip
            result.cost_usd = lesson.cost_usd
            result.returns = len(lesson.returns)
            result.frames = [_frame(f, lesson_folder, out) for f in lesson.frames]
        else:
            planned = plan(cell.topic, lesson_folder, wishes=wishes, config_path=config,
                           client=planner_client)  # fmt: skip
            result.cost_usd = planned.cost_usd
        _planner_numbers(result, lesson_folder)
    except Exception as error:  # one cell must not stop the others
        result.error = f"{type(error).__name__}: {error}"
        _planner_numbers(result, folder / LESSON)
    result.seconds = round(time.perf_counter() - started, 1)
    return result


def _frame(frame: Any, lesson: Path, out: Path) -> FrameResult:
    """A frame's numbers, from lesson.json's line and its run folder."""
    run = lesson / frame.folder if frame.folder else None
    codes: tuple[str, ...] = ()
    calls = 0
    picture = None
    if run is not None:
        report = _json(run / "report.json")
        codes = tuple(i["code"] for i in report.get("issues", ()) if not i.get("allowed_because"))
        calls = int(_json(run / "agent" / "session.json").get("calls", 0))
        if (run / "frame.png").exists():
            picture = str((run / "frame.png").relative_to(out))
    return FrameResult(
        frame.frame, frame.status, frame.turns, calls, frame.returns, frame.cost_usd, codes,
        picture,
    )  # fmt: skip


def _planner_numbers(result: CellResult, lesson: Path) -> None:
    """The first plan's answers and problems, the planner's cost, the lesson planned."""
    records = _json(lesson / "planner" / "session.json")
    sessions = records.get("sessions", [])
    if sessions:
        answers = sessions[0].get("answers", [])
        result.answers = len(answers)
        result.problems = sum(len(a.get("problems", [])) for a in answers)
    result.planner_cost_usd = float(records.get("cost_usd", 0.0))
    plan_file = _json(lesson / "lesson_plan.json")
    if plan_file:
        result.planned = True
        result.lesson = str(plan_file.get("id", ""))
        result.planned_frames = len(plan_file.get("frames", []))
    if not result.cost_usd:
        result.cost_usd = result.planner_cost_usd


def _json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}
