"""The way back to the planner: the agent's ask_planner ends the session and routes the frame
to the planner, with its request."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from irpipe.agent import run_agent
from irpipe.agent.sandbox import Sandbox
from irpipe.orchestrator.routing import Destination
from irpipe.schema.request import PlannerRequest

ROOT = Path(__file__).parent.parent.parent
TANGENTS = ROOT / "examples" / "tangents"
SCRIPT = (TANGENTS / "build_ir.py").read_text(encoding="utf-8")
_ALLOW = SCRIPT.index('pic.allow("W-FILL-OVERLAP"')
WARNED = SCRIPT[:_ALLOW] + SCRIPT[SCRIPT.index("\n", SCRIPT.index('"P"])', _ALLOW)) + 1 :]
"""The example without its allow entry: one open warning (W-FILL-OVERLAP)."""


def ask(body: str) -> str:
    return f'I cannot fit it.\n<call tool="ask_planner">{body}</call>'


SPLIT = ask('{"request": "split", "reason": "two ideas in one frame", "items": ["region"]}')


def session(tmp_path: Path, config: Path, client: Any) -> Any:
    return run_agent(
        TANGENTS / "brief.json", tmp_path / "out", config_path=config, client=client,
        sandbox=Sandbox("audit"),
    )  # fmt: skip


def test_asking_the_planner_ends_it_and_the_report_routes_the_frame_there(
    tmp_path: Path, agent_config: Callable[..., Path], scripted: Callable[..., Any]
) -> None:
    run = f'<call tool="run_python">\n{WARNED}\n</call>'
    client = scripted(run, '<call tool="submit"></call>', SPLIT)
    result = session(tmp_path, agent_config(), client)
    assert result.ended == "the agent asked the planner to split the brief"
    assert result.request == PlannerRequest(
        frame="tangents", kind="split", reason="two ideas in one frame", items=("region",)
    )
    report, route = result.outcome.report, result.outcome.route
    assert [i.code for i in report.issues] == ["W-FILL-OVERLAP", "E-REPLAN"]
    assert report.issues[-1].message == (
        "the agent asks the planner to split it in two: two ideas in one frame (region)"
    )
    assert route.to is Destination.PLANNER and [i.code for i in route.issues] == ["E-REPLAN"]
    out = tmp_path / "out"
    assert result.chosen == 1 and (out / "frame.png").exists()  # the best turn is kept
    written = json.loads((out / "report.json").read_text())
    assert [i["code"] for i in written["issues"]] == ["W-FILL-OVERLAP", "E-REPLAN"]
    asked = json.loads((out / "agent" / "planner_request.json").read_text())
    assert asked["kind"] == "split" and asked["version"] == "planner-request/1.0"
    session_record = json.loads((out / "agent" / "session.json").read_text())
    assert session_record["planner_request"]["items"] == ["region"]


def test_asking_before_any_turn_stops_at_the_agent_and_draws_nothing(
    tmp_path: Path, agent_config: Callable[..., Path], scripted: Callable[..., Any]
) -> None:
    client = scripted(ask('{"request": "shorten", "reason": "five labels on one curve"}'))
    result = session(tmp_path, agent_config(), client)
    report = result.outcome.report
    assert (report.stopped_at, [i.code for i in report.issues]) == ("agent", ["E-REPLAN"])
    assert result.outcome.route.to is Destination.PLANNER and result.chosen is None
    assert not (tmp_path / "out" / "frame.png").exists()
    assert [p.name for p in result.outcome.files] == ["report.json"]


def test_a_request_that_is_not_one_is_answered_and_the_session_goes_on(
    tmp_path: Path, agent_config: Callable[..., Path], scripted: Callable[..., Any]
) -> None:
    client = scripted(
        ask('{"request": "merge", "reason": "x"}'),
        ask('{"request": "split"}'),
        ask('{"request": "split", "reason": "x", "items": [1]}'),
        SPLIT,
    )
    result = session(tmp_path, agent_config(), client)
    said = [text.split("\n")[1] for text in client.results()]
    assert said == [
        'request is "shorten" or "split", not "merge"',
        "'reason' is required: say what does not fit, and where",
        "'items' is a list of the must_show ids or texts that do not fit",
    ]
    assert result.request is not None and result.calls == 4
