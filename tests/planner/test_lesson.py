"""A whole lesson: planned, every frame drawn, a frame that does not fit sent back and drawn
again; lesson.json. First with the real agent (scripted models), then the loop's rules with
a stand-in agent."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from irpipe.agent import AgentError, AgentResult
from irpipe.agent.sandbox import Sandbox
from irpipe.agent.session import E_REPLAN
from irpipe.core import Report
from irpipe.orchestrator.inputs import E_BRIEF
from irpipe.orchestrator.routing import route
from irpipe.orchestrator.run import E_INTERNAL, Outcome
from irpipe.planner import Return, fix_request, run_lesson
from irpipe.schema.request import PlannerRequest

type Config = Callable[..., Path]

SUBMIT = '<call tool="submit"></call>'
SHORTEN = PlannerRequest(frame="projection", kind="shorten", reason="the formula does not fit")


def drawn(kit: Any) -> list[str]:
    """The agent's replies that draw the example frame READY."""
    return [f'<call tool="run_python">\n{kit.SCRIPT}\n</call>', SUBMIT]


def summary(folder: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((folder / "lesson.json").read_text())
    return data


def test_a_lesson_is_planned_and_every_frame_drawn(
    tmp_path: Path, planner_config: Config, scripted: Callable[..., Any], kit: Any
) -> None:
    folder = tmp_path / "lesson"
    result = run_lesson(
        "vector projection", folder, config_path=planner_config(),
        planner_client=scripted(kit.ONE), agent_client=scripted(*drawn(kit)),
        sandbox=Sandbox("audit"),
    )  # fmt: skip
    assert result.ready and result.ended == "1 of 1 frames are READY"
    assert (folder / "runs" / "projection" / "frame.png").exists()
    assert summary(folder) == {
        "topic": "vector projection", "lesson": "vector_projection", "ready": True,
        "ended": "1 of 1 frames are READY",
        "frames": [{"frame": "projection", "status": "READY", "next": "done: the picture is ready",
                    "turns": 1, "returns": 0, "cost_usd": 0.02, "folder": "runs/projection"}],
        "returns": [], "cost_usd": 0.03,
    }  # fmt: skip


def test_a_frame_the_agent_cannot_fit_is_shortened_and_drawn_again(
    tmp_path: Path, planner_config: Config, scripted: Callable[..., Any], kit: Any
) -> None:
    folder = tmp_path / "lesson"
    ask = '<call tool="ask_planner">{"request": "shorten", "reason": "too much"}</call>'
    shorter = kit.answer(
        kit.lesson(("projection", "define")), [kit.brief(composition_notes="Less, larger.")]
    )
    planner = scripted(kit.ONE, shorter)
    result = run_lesson(
        "vector projection", folder, config_path=planner_config(), planner_client=planner,
        agent_client=scripted(ask, *drawn(kit)), sandbox=Sandbox("audit"),
    )  # fmt: skip
    assert result.ready
    assert result.returns == [Return("projection", "shorten", "too much", ("projection",))]
    assert result.frames[0].returns == 1
    kept = folder / "runs" / "projection.1"  # the run that went back
    assert json.loads((kept / "agent" / "planner_request.json").read_text())["kind"] == "shorten"
    assert planner.sent[1][0].text.startswith("Frame 'projection' cannot be drawn")
    brief = json.loads((folder / "projection.brief.json").read_text())
    assert brief["composition_notes"] == "Less, larger."


def stand_in(steps: dict[str, list[Any]], calls: list[str]) -> Callable[..., AgentResult]:
    """An agent that, for each frame in turn, draws it READY, leaves ``issues`` open, asks the
    planner (a PlannerRequest) or fails (an exception), as ``steps`` say; READY after them."""

    def run(brief_path: Path, folder: Path, **_: Any) -> AgentResult:
        frame = brief_path.name.removesuffix(".brief.json")
        calls.append(frame)
        folder.mkdir(parents=True, exist_ok=True)
        step = steps[frame].pop(0) if steps.get(frame) else []
        if isinstance(step, Exception):
            raise step
        request = step if isinstance(step, PlannerRequest) else None
        issues = [E_REPLAN("asked")] if request else list(step)
        report = Report.build(issues)
        outcome = Outcome(folder, report, route(report), ())
        return AgentResult(outcome, cost_usd=0.02, request=request)

    return run


def lesson_with(
    tmp_path: Path,
    config: Path,
    planner: Any,
    steps: dict[str, list[Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Any, list[str]]:
    calls: list[str] = []
    monkeypatch.setattr("irpipe.planner.lesson.run_agent", stand_in(steps, calls))
    result = run_lesson("x", tmp_path / "lesson", config_path=config, planner_client=planner)
    return result, calls


def test_a_split_frame_is_drawn_as_two_and_the_others_are_not_drawn_again(
    tmp_path: Path, planner_config: Config, scripted: Callable[..., Any], kit: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    frames = [("two_vectors", "introduce"), ("shadow", "define"), ("formula", "define"),
              ("recap", "summary")]  # fmt: skip
    split = kit.answer(kit.lesson(*frames), [kit.brief("shadow"), kit.brief("formula")])
    asks = PlannerRequest(frame="projection", kind="split", reason="two ideas")
    result, calls = lesson_with(
        tmp_path, planner_config(), scripted(kit.THREE, split), {"projection": [asks]}, monkeypatch
    )
    assert calls == ["two_vectors", "projection", "shadow", "formula", "recap"]
    assert [(f.frame, f.status, f.returns) for f in result.frames] == [
        ("two_vectors", "READY", 0), ("shadow", "READY", 1), ("formula", "READY", 1),
        ("recap", "READY", 0),
    ]  # fmt: skip
    assert result.returns[0].became == ("shadow", "formula")
    assert result.cost_usd == pytest.approx(0.02 * 5 + 0.01 * 2)


def test_a_frame_goes_back_at_most_max_returns_times(
    tmp_path: Path, planner_config: Config, scripted: Callable[..., Any], kit: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    config = planner_config(max_returns=1)
    shorter = kit.answer(kit.lesson(("projection", "define")), [kit.brief(focus=[])])
    result, calls = lesson_with(
        tmp_path, config, scripted(kit.ONE, shorter), {"projection": [SHORTEN, SHORTEN]},
        monkeypatch,
    )  # fmt: skip
    assert calls == ["projection", "projection"] and len(result.returns) == 1
    frame = result.frames[0]
    assert (frame.status, frame.returns) == ("NOT_READY", 1)
    assert frame.next == "planner: 1 issue to fix in the brief"
    assert not result.ready and summary(tmp_path / "lesson")["ready"] is False


def test_open_brief_issues_go_back_as_a_fix_request(
    tmp_path: Path, planner_config: Config, scripted: Callable[..., Any], kit: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    wrong = E_BRIEF("the font pair is not offered", path="render_profile", hint="Inter")
    planner = scripted(kit.ONE, kit.ONE)
    result, _ = lesson_with(
        tmp_path, planner_config(), planner, {"projection": [[wrong]]}, monkeypatch
    )
    assert result.ready and result.returns[0].kind == "fix"
    asked = planner.sent[1][0].text
    assert "E-BRIEF: the font pair is not offered (at render_profile); hint: Inter" in asked
    assert fix_request("f", [wrong]).issues == (
        "E-BRIEF: the font pair is not offered (at render_profile); hint: Inter",
    )


def test_a_frame_for_a_person_stops_the_lesson_and_one_without_a_picture_does_not(
    tmp_path: Path, planner_config: Config, scripted: Callable[..., Any], kit: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    steps: dict[str, list[Any]] = {
        "two_vectors": [AgentError("the model could not answer")],
        "projection": [[E_INTERNAL("a stage crashed")]],
    }
    result, calls = lesson_with(tmp_path, planner_config(), scripted(kit.THREE), steps, monkeypatch)
    assert calls == ["two_vectors", "projection"]
    assert [(f.frame, f.status) for f in result.frames] == [
        ("two_vectors", "NO_PICTURE"), ("projection", "NOT_READY"), ("recap", "NOT_DRAWN"),
    ]  # fmt: skip
    assert result.frames[0].next == "the agent made no picture: the model could not answer"
    assert result.ended == (
        "frame 'projection' needs a person (human: 1 issue that the agent cannot fix); "
        "the lesson stopped"
    )
