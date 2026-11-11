"""The planner (analysis §1, wave 2): a language model that turns a topic into a lesson plan
and a brief per frame, and changes a brief that cannot be drawn.

    result = plan("vector projection", Path("lessons/projection"))
    result = revise(request, Path("lessons/projection"))      # shorten, split or fix a frame
    lesson = run_lesson("vector projection", Path("lessons/projection"))   # plan and draw

The model answers with JSON; each answer is checked as the orchestrator
reads a brief, and its problems go back to the model. The model is reached
through the agent's LLM clients (K10). ``run_lesson`` draws every frame
with the IR agent and sends a frame that does not fit back to the planner,
at the agent's request or for the issues of its run.

Module map:
    settings.py    PlannerSettings: pipeline.toml's [planner]
    wishes.py      Wishes: what the user asked for, laid over the planner's choice
    prompt.py      the system prompt, the first message of a plan or a revision, problems
    answer.py      the answer's JSON, its draft files, and what is wrong with them
    session.py     plan() and revise(): the loop, the lesson folder, records
    lesson.py      run_lesson(): plan, draw each frame, send it back, lesson.json
"""

from irpipe.planner.lesson import FrameRun, LessonResult, Return, fix_request, run_lesson
from irpipe.planner.session import PlannerError, PlanResult, plan, revise
from irpipe.planner.settings import PlannerSettings
from irpipe.planner.wishes import Wishes

__all__ = [
    "FrameRun",
    "LessonResult",
    "PlanResult",
    "PlannerError",
    "PlannerSettings",
    "Return",
    "Wishes",
    "fix_request",
    "plan",
    "revise",
    "run_lesson",
]
