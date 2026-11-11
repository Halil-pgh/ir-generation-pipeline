"""The planner without a real model: a scripted client, answers made from the example, a config.

``scripted(*replies)`` is an LLM client that answers with ``replies`` in
order (an exception is raised instead) and keeps what it was sent. ``kit``
holds what builds answers from examples/projection: ``kit.lesson(...)``, its
lesson plan with the frames asked for; ``kit.brief(...)``, its brief under
another id and purpose; ``kit.answer(...)``, a reply; ``kit.ONE`` and
``kit.THREE``, lessons of one and three frames; ``kit.SCRIPT``, its
build_ir.py. ``planner_config(**planner)`` is the repository's
pipeline.toml, drawing with SVG, with these ``[planner]`` settings and both
examples found from anywhere. Tests marked ``llm`` call the real model; they
run only with IRPIPE_LLM=1.
"""

import json
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from irpipe.agent import AgentSettings, LLMClient, LLMError, Message, Reply

ROOT = Path(__file__).parent.parent.parent
EXAMPLE = ROOT / "examples" / "projection"
LESSON: dict[str, Any] = json.loads((EXAMPLE / "lesson_plan.json").read_text(encoding="utf-8"))
BRIEF: dict[str, Any] = json.loads((EXAMPLE / "brief.json").read_text(encoding="utf-8"))
SCRIPT = (EXAMPLE / "build_ir.py").read_text(encoding="utf-8")


class Scripted(LLMClient):
    name = "scripted"

    def __init__(self, *replies: str | Exception) -> None:
        super().__init__(AgentSettings())
        self.replies = list(replies)
        self.sent: list[list[Message]] = []
        self.systems: list[str] = []

    def complete(self, system: str, messages: Sequence[Message]) -> Reply:
        self.sent.append(list(messages))
        self.systems.append(system)
        if not self.replies:
            raise AssertionError("the scripted client ran out of replies")
        answer = self.replies.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return Reply(answer, cost_usd=0.01)


def lesson(*frames: tuple[str, str], **changes: Any) -> dict[str, Any]:
    """The example's lesson plan with these (id, purpose) frames."""
    outlines = [{"id": i, "purpose": p, "summary": f"the frame {i}"} for i, p in frames]
    return {**LESSON, "frames": outlines, **changes}


def brief(frame_id: str = "projection", purpose: str = "define", **changes: Any) -> dict[str, Any]:
    """The example's brief under this id and purpose."""
    return {**BRIEF, "id": frame_id, "purpose": purpose, **changes}


def answer(plan: dict[str, Any], briefs: list[dict[str, Any]]) -> str:
    """A reply holding the answer in a fence, after a line of prose."""
    body = json.dumps({"lesson_plan": plan, "briefs": briefs}, indent=2)
    return f"Here is the lesson.\n\n```json\n{body}\n```\n"


ONE = answer(lesson(("projection", "define")), [brief()])
"""A lesson of one frame, the example's."""
THREE = answer(
    lesson(("two_vectors", "introduce"), ("projection", "define"), ("recap", "summary")),
    [brief("two_vectors", "introduce"), brief(), brief("recap", "summary")],
)
"""A lesson of three frames, each the example's brief under its id and purpose."""


@pytest.fixture
def scripted() -> Callable[..., Scripted]:
    return lambda *replies: Scripted(*replies)


@pytest.fixture
def kit() -> SimpleNamespace:
    return SimpleNamespace(
        lesson=lesson, brief=brief, answer=answer, ONE=ONE, THREE=THREE, SCRIPT=SCRIPT,
        LESSON=LESSON, BRIEF=BRIEF, LLMError=LLMError,
    )  # fmt: skip


@pytest.fixture
def planner_config(tmp_path: Path) -> Callable[..., Path]:
    """``planner_config(**planner)``: pipeline.toml with SVG and these ``[planner]`` settings."""

    def make(**planner: object) -> Path:
        text = (ROOT / "pipeline.toml").read_text(encoding="utf-8")
        text = text.replace('backend = "manim"', 'backend = "svg"')
        head, agent = text.split("[agent]\n")
        head = head.replace('# example = "examples/projection"', f'example = "{EXAMPLE}"')
        for key, value in planner.items():
            line = f"{key} = " + (f'"{value}"' if isinstance(value, str) else str(value))
            rows = head.splitlines()
            found = [n for n, row in enumerate(rows) if row.split("=")[0].strip() == key]
            if found:
                rows[found[-1]] = line  # the [planner] table is the last one before [agent]
            else:
                rows.append(line)
            head = "\n".join(rows) + "\n"
        tangents = ROOT / "examples" / "tangents" / "build_ir.py"
        text = f'{head}[agent]\n{agent}\nexample = "{tangents}"\n'
        path = tmp_path / "pipeline.toml"
        path.write_text(text, encoding="utf-8")
        return path

    return make


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if os.environ.get("IRPIPE_LLM") == "1":
        return
    skip = pytest.mark.skip(reason="calls the real model; set IRPIPE_LLM=1 to run it")
    for item in items:
        if "llm" in item.keywords:
            item.add_marker(skip)
