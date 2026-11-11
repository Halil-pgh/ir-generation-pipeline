"""The agent without a real model: a scripted client, a pipeline drawing with SVG, a folder.

``scripted(*replies)`` is an LLM client that answers with ``replies`` in
order (a reply may be a function of the messages so far) and keeps what it
was sent. ``agent_config`` is the repository's pipeline.toml, drawing with
the SVG backend, with the example script found from anywhere.
Tests marked ``llm`` call the real model; they run only with IRPIPE_LLM=1.
"""

import os
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from irpipe.agent import AgentSettings, LLMClient, Message, Reply
from irpipe.schema.ir import HEADER_FIELDS

ROOT = Path(__file__).parent.parent.parent
type Answer = str | Callable[[Sequence[Message]], str]


class Scripted(LLMClient):
    name = "scripted"

    def __init__(self, replies: Sequence[Answer]) -> None:
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
        return Reply(answer(messages) if callable(answer) else answer, cost_usd=0.001)

    def results(self) -> list[str]:
        """What came back to the model after each of its replies."""
        return [sent[-1].text for sent in self.sent[1:]]


@pytest.fixture
def header(ir: Callable[..., dict[str, object]]) -> dict[str, object]:
    """The shared test header (tests/conftest.py), as a dict."""
    return {name: value for name, value in ir([]).items() if name in HEADER_FIELDS}


@pytest.fixture
def scripted() -> Callable[..., Scripted]:
    return lambda *replies: Scripted(replies)


@pytest.fixture
def agent_config(tmp_path: Path) -> Callable[..., Path]:
    """``agent_config(**agent)``: pipeline.toml with SVG and these ``[agent]`` settings."""

    def make(**agent: object) -> Path:
        text = (ROOT / "pipeline.toml").read_text(encoding="utf-8")
        text = text.replace('backend = "manim"', 'backend = "svg"')
        example = ROOT / "examples" / "tangents" / "build_ir.py"
        text += f'\nexample = "{example}"\n'
        for key, value in agent.items():
            line = f"{key} = " + (f'"{value}"' if isinstance(value, str) else str(value))
            text = "\n".join(
                line if row.split("=")[0].strip() == key else row for row in text.splitlines()
            )
            if line not in text:
                text += f"\n{line}\n"
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
