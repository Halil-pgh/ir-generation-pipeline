"""The call protocol, the settings, the IR reference and what the model is told."""

from pathlib import Path

import pytest

from irpipe.agent import AgentSettings
from irpipe.agent.prompt import first_message, system_prompt, wrap
from irpipe.agent.protocol import parse
from irpipe.agent.reference import object_reference
from irpipe.agent.tools import NAMES
from irpipe.core import PipelineConfig, load_config
from irpipe.core.errors import PipelineConfigError
from irpipe.core.plugins import load_plugins
from irpipe.irkit.fields import object_models
from irpipe.orchestrator.inputs import read_inputs

ROOT = Path(__file__).parent.parent.parent
load_plugins(["irpipe.components"])


def test_a_message_holds_one_call_whose_body_is_taken_as_it_is() -> None:
    parsed = parse('I measure first.\n<call tool="measure_tex">{"tex": "a<b"}</call>')
    assert parsed.call is not None and parsed.problem is None
    assert (parsed.call.tool, parsed.call.body) == ("measure_tex", '{"tex": "a<b"}')
    fenced = parse('<call tool="run_python">\n```python\nprint(1 < 2)\n```\n</call>')
    assert fenced.call is not None and fenced.call.body == "print(1 < 2)"
    assert parse('<call tool="check"></call>').call == parse('<call tool="check" ></call>').call


@pytest.mark.parametrize(
    ("message", "said"),
    [
        ("I am done.", "holds no tool call"),
        ('<call tool="run_python">\nprint(1)', "was not closed with </call>"),
    ],
)
def test_a_message_that_breaks_the_protocol_is_told_how(message: str, said: str) -> None:
    parsed = parse(message)
    assert parsed.call is None and parsed.problem is not None and said in parsed.problem


def test_of_several_calls_only_the_first_runs() -> None:
    parsed = parse('<call tool="validate"></call> and <call tool="submit"></call>')
    assert parsed.call is not None and parsed.call.tool == "validate"
    assert parsed.problem is not None and "only the first (validate) ran" in parsed.problem


def test_settings_come_from_the_agent_table_and_a_typo_fails() -> None:
    settings = AgentSettings.from_config(load_config(ROOT / "pipeline.toml"))
    assert (settings.provider, settings.model, settings.max_turns) == (
        "claude-cli", "claude-haiku-5-5", 3,
    )  # fmt: skip
    with pytest.raises(PipelineConfigError, match=r"\[agent\]: max_turn"):
        AgentSettings.from_config(PipelineConfig(agent={"max_turn": 3}))


def test_the_reference_has_every_type_and_field_written_short() -> None:
    text = object_reference()
    for name in object_models():
        assert f"## {name} (" in text
    assert "## Label (the value of a field)" in text and "## CubicTo" in text
    assert "  center: point (required)" in text  # circle
    assert "  fill: color" in text and "  clip: region" in text
    assert "  radius: number (required)" in text  # expressions allowed
    assert "  stroke_width: float" in text  # no expressions
    assert '  arrows: ["start" | "mid" | "end", ...]' in text


def test_the_system_prompt_holds_the_tools_the_sdk_the_ir_and_the_example() -> None:
    settings = AgentSettings(max_turns=2, max_calls=12)
    example = (ROOT / "examples" / "tangents" / "build_ir.py").read_text(encoding="utf-8")
    system = system_prompt(settings, example)
    for name in NAMES:
        assert f"- {name}:" in system
    assert '<call tool="NAME">BODY</call>' in system
    assert "You have 2 submissions and 12 messages in all." in system
    assert "## irpipe.irkit.geometry" in system and "## circle (object)" in system
    assert example.strip() in system
    assert system_prompt(settings, None).count("# An example") == 0


def test_the_first_message_gives_the_brief_its_lesson_and_the_header() -> None:
    inputs, _ = read_inputs(ROOT / "examples" / "projection" / "brief.json")
    assert inputs is not None
    first = first_message(inputs)
    assert '"intent": "The projection of a onto b is the shadow a casts on b"' in first
    assert "<lesson>" in first and "Projecting one vector onto another" in first
    assert '"safe": [' in first and "Picture.open() reads it" in first


def test_a_result_comes_back_cut_to_its_limit_with_the_budget() -> None:
    wrapped = wrap("check", "x" * 700, calls_left=5, turns_left=1, limit=500)
    assert wrapped.startswith('<result tool="check">\n' + "x" * 500 + "\n… (200 more characters")
    assert wrapped.endswith("(messages left: 5, submissions left: 1)")
