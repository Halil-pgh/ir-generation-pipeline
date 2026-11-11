"""A whole session with a scripted model: turns, when it stops, which turn is kept, records."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from irpipe.agent import LLM_CLIENTS, AgentError, LLMError, run_agent
from irpipe.agent.sandbox import Sandbox
from irpipe.orchestrator.routing import Destination

ROOT = Path(__file__).parent.parent.parent
TANGENTS = ROOT / "examples" / "tangents"
SCRIPT = (TANGENTS / "build_ir.py").read_text(encoding="utf-8")
_ALLOW = SCRIPT.index('pic.allow("W-FILL-OVERLAP"')
WARNED = SCRIPT[:_ALLOW] + SCRIPT[SCRIPT.index("\n", SCRIPT.index('"P"])', _ALLOW)) + 1 :]
"""The example without its allow entry: one open warning (W-FILL-OVERLAP)."""
WORSE = WARNED.replace(', covers=["region"]', "")
"""Two open warnings: the overlap, and the region no longer covered."""


def run(python: str) -> str:
    return f'<call tool="run_python">\n{python}\n</call>'


SUBMIT = '<call tool="submit"></call>'


def session(
    tmp_path: Path, config: Path, client: Any, brief: Path = TANGENTS / "brief.json"
) -> Any:
    return run_agent(
        brief, tmp_path / "out", config_path=config, client=client, sandbox=Sandbox("audit")
    )


def record(tmp_path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((tmp_path / "out" / "agent" / "session.json").read_text())
    return data


def test_a_ready_turn_ends_the_session_and_fills_the_run_folder(
    tmp_path: Path, agent_config: Callable[..., Path], scripted: Callable[..., Any]
) -> None:
    client = scripted(run(SCRIPT), '<call tool="check"></call>', SUBMIT)
    result = session(tmp_path, agent_config(), client)
    assert (result.chosen, result.ended, result.calls) == (1, "turn 1 is READY", 3)
    assert result.outcome.report.ready and result.outcome.route.to is Destination.DONE
    out = tmp_path / "out"
    assert (out / "frame.png").exists() and (out / "build_ir.py").read_text() == SCRIPT
    assert (out / "agent" / "turns" / "1" / "report.json").exists()
    assert record(tmp_path)["turns"] == [
        {"turn": 1, "status": "READY", "open_errors": 0, "open_warnings": 0,
         "next": "done: the picture is ready"},
    ]  # fmt: skip
    assert record(tmp_path)["cost_usd"] == pytest.approx(0.003)
    system = (out / "agent" / "system_prompt.md").read_text()
    assert system == client.systems[0] and SCRIPT.strip() in system  # the example
    assert client.results()[-1].startswith('<result tool="check">\n0 errors, 0 warnings, 1 allowed')
    transcript = (out / "agent" / "transcript.md").read_text()
    assert (
        transcript.count("## assistant") == 3
        and "Draw the frame this brief describes." in transcript
    )


def test_a_turn_that_does_no_better_ends_it_and_the_better_turn_is_kept(
    tmp_path: Path, agent_config: Callable[..., Path], scripted: Callable[..., Any]
) -> None:
    client = scripted(run(WARNED), SUBMIT, run(WORSE), SUBMIT)
    result = session(tmp_path, agent_config(), client)
    assert result.ended == "turn 2 did no better than turn 1 (no progress)"
    assert [t.counts for t in result.turns] == [(0, 1), (0, 2)]
    assert result.chosen == 1 and (tmp_path / "out" / "build_ir.py").read_text() == WARNED
    said = client.results()[1]
    assert said.startswith('<result tool="submit">\nturn 1: NOT READY')
    assert "W-FILL-OVERLAP" in said and said.endswith("(messages left: 28, submissions left: 2)")


def test_the_turn_limit_ends_it(
    tmp_path: Path, agent_config: Callable[..., Path], scripted: Callable[..., Any]
) -> None:
    result = session(tmp_path, agent_config(max_turns=1), scripted(run(WARNED), SUBMIT))
    assert result.ended == "all 1 turns are used" and result.chosen == 1


def test_a_submission_that_fails_validate_is_not_a_turn(
    tmp_path: Path, agent_config: Callable[..., Path], scripted: Callable[..., Any]
) -> None:
    broken = SCRIPT.replace("radius=r, space=S", "radius=-r, space=S")
    client = scripted(run(broken), SUBMIT, run(SCRIPT), SUBMIT)
    result = session(tmp_path, agent_config(), client)
    assert client.results()[1].startswith(
        '<result tool="submit">\nnot accepted: build_ir.py must pass validate first.'
    )
    assert [t.number for t in result.turns] == [1] and result.outcome.report.ready


def test_when_the_messages_run_out_the_last_script_is_still_drawn(
    tmp_path: Path, agent_config: Callable[..., Path], scripted: Callable[..., Any]
) -> None:
    client = scripted("Let me think.", run(WARNED))
    result = session(tmp_path, agent_config(max_calls=2), client)
    assert client.results()[0].startswith(
        '<result tool="protocol">\nyour message holds no tool call'
    )
    assert result.ended == ("the model used all 2 messages; its last script was compiled as a turn")
    assert result.chosen == 1 and result.turns[0].counts == (0, 1)


def test_a_last_script_that_fails_is_still_a_turn_the_report_can_send_back(
    tmp_path: Path, agent_config: Callable[..., Path], scripted: Callable[..., Any]
) -> None:
    client = scripted(run("raise ValueError('no b vector')"))
    result = session(tmp_path, agent_config(max_calls=1), client)
    report = result.outcome.report
    assert (report.stopped_at, [i.code for i in report.issues]) == ("script", ["E-SCRIPT"])
    assert result.outcome.route.to is Destination.AGENT and result.chosen == 1


def test_the_command_prints_each_turn_and_the_chosen_report(
    tmp_path: Path,
    agent_config: Callable[..., Path],
    scripted: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from irpipe.agent import session as session_module
    from irpipe.cli import main

    client = scripted(run(WARNED), SUBMIT, run(SCRIPT), SUBMIT)
    monkeypatch.setattr(LLM_CLIENTS, "get", lambda name: lambda settings: client)
    monkeypatch.setattr(session_module, "sandbox_for", lambda kind, memory: Sandbox("audit"))
    out = tmp_path / "out"
    status = main(
        ["agent", str(TANGENTS / "brief.json"), "-o", str(out), "--config", str(agent_config())]
    )
    printed = capsys.readouterr().out.splitlines()
    assert status == 0
    assert printed[:3] == [
        "turn 1: NOT READY (0 errors, 1 warning)",
        "turn 2: READY (0 errors, 0 warnings)",
        "chose turn 2 (4 messages, $0.0040); turn 2 is READY",
    ]
    assert printed[-1] == "next: done: the picture is ready"


def test_a_model_that_cannot_answer_ends_it_and_without_a_script_nothing_is_drawn(
    tmp_path: Path, agent_config: Callable[..., Path], scripted: Callable[..., Any]
) -> None:
    def fail(messages: Any) -> str:
        raise LLMError("the model answered with an error: limit reached")

    with pytest.raises(AgentError, match=r"the model could not answer: .* limit reached"):
        session(tmp_path, agent_config(), scripted(fail))
    assert record(tmp_path)["turns"] == [] and record(tmp_path)["chosen_turn"] is None


def test_a_broken_brief_stops_before_the_model_is_asked(
    tmp_path: Path, agent_config: Callable[..., Path], scripted: Callable[..., Any]
) -> None:
    brief = json.loads((TANGENTS / "brief.json").read_text())
    (tmp_path / "brief.json").write_text(json.dumps({**brief, "focus": ["nothing"]}))
    client = scripted()
    result = session(tmp_path, agent_config(), client, brief=tmp_path / "brief.json")
    assert result.outcome.route.to is Destination.PLANNER and client.sent == []
    assert result.ended.startswith("stopped before the agent: planner")


@pytest.mark.llm
def test_the_agent_draws_the_teams_brief_ready_with_the_real_model(tmp_path: Path) -> None:
    result = run_agent(
        ROOT / "examples" / "projection" / "brief.json", tmp_path / "out",
        config_path=ROOT / "pipeline.toml",
    )  # fmt: skip
    assert result.outcome.report.ready, (result.ended, result.outcome.report.issues)
