"""The orchestrator's parts: header, inputs, environment, script, coverage, routing, records."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from irpipe.core import ISSUE_CODES, Issue, Report
from irpipe.core.config import load_config
from irpipe.orchestrator import environment
from irpipe.orchestrator.coverage import coverage_issues
from irpipe.orchestrator.header import STYLES, header_for
from irpipe.orchestrator.inputs import read_inputs
from irpipe.orchestrator.records import alt_text
from irpipe.orchestrator.routing import Destination, route
from irpipe.orchestrator.run import E_INTERNAL
from irpipe.orchestrator.script import run_script
from irpipe.schema.brief import FrameBrief, frame_style
from irpipe.schema.ir import IRDocument, IRHeader

ROOT = Path(__file__).parent.parent.parent
EXAMPLE = ROOT / "examples" / "projection"


def example_ir() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((EXAMPLE / "ir.json").read_text(encoding="utf-8"))
    return data


# The header


def test_the_header_from_the_example_brief_is_the_example_pictures_header() -> None:
    inputs, issues = read_inputs(EXAMPLE / "brief.json")
    assert inputs is not None and issues == []
    raw = example_ir()
    assert inputs.header == IRHeader.model_validate(
        {k: raw[k] for k in IRHeader.model_fields if k in raw}
    )
    assert inputs.header.styles.keys() == STYLES.keys()


def test_a_subtitle_band_and_a_platform_reach_the_header() -> None:
    changes = {"aspect": "9:16", "platform": "tiktok", "subtitle": {"mode": "reserve"}}
    brief = FrameBrief.model_validate(brief_data(lesson=None, render_profile=changes))
    frame = header_for(brief, frame_style(brief)).frame
    assert (frame.aspect, frame.pixels, frame.platform) == ("9:16", (1080, 1920), "tiktok")
    assert frame.units == (9, 16)
    assert frame.subtitle.mode == "reserve" and frame.subtitle.band is not None
    assert frame.safe[1] == frame.subtitle.band[3]  # the safe area ends on the band


# Inputs: what the planner wrote


def write(folder: Path, name: str, data: Any) -> Path:
    path = folder / name
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


def brief_data(**changes: Any) -> dict[str, Any]:
    data = json.loads((EXAMPLE / "brief.json").read_text(encoding="utf-8"))
    return {**data, **changes}


@pytest.mark.parametrize(
    ("brief", "path", "message"),
    [
        ("{not json", None, "brief.json: "),
        (brief_data(purpos="define"), "purpos", "brief.json: unknown field 'purpos'"),
        (brief_data(focus=["shadw"]), None, "brief.json: focus names 'shadw'"),
        (brief_data(id="extra"), None, "lesson 'vector_projection' has no frame 'extra'"),
    ],
)
def test_what_the_planner_got_wrong_goes_back_to_it(
    tmp_path: Path, brief: Any, path: str | None, message: str
) -> None:
    shutil.copy(EXAMPLE / "lesson_plan.json", tmp_path / "lesson_plan.json")
    inputs, issues = read_inputs(write(tmp_path, "brief.json", brief))
    assert inputs is None
    (issue,) = issues
    assert (issue.code, str(issue.origin)) == ("E-BRIEF", "infeasible")
    assert issue.message.startswith(message)
    if path:
        assert issue.path == path


def test_a_lesson_is_needed_when_the_brief_names_one(tmp_path: Path) -> None:
    (issue,) = read_inputs(write(tmp_path, "brief.json", brief_data()))[1]
    assert "belongs to lesson 'vector_projection', whose plan is not here" in issue.message


def test_a_font_pair_the_project_does_not_offer_is_refused(tmp_path: Path) -> None:
    fonts = {"typography": {"font_pair": {"text": "Comic Sans", "math": "latin-modern"}}}
    brief = brief_data(lesson=None, render_profile={"aspect": "16:9", **fonts})
    (issue,) = read_inputs(write(tmp_path, "brief.json", brief))[1]
    assert (
        issue.message == "the font pair Comic Sans with latin-modern is not one the project offers"
    )
    assert issue.hint == "Inter with latin-modern"


def test_a_profile_that_makes_no_frame_is_the_planners_to_change(tmp_path: Path) -> None:
    brief = brief_data(lesson=None, render_profile={"aspect": "16:9", "platform": "tiktok"})
    (issue,) = read_inputs(write(tmp_path, "brief.json", brief))[1]
    assert issue.message.startswith("the render profile makes no frame: platform 'tiktok'")


# Environment


def header() -> IRHeader:
    raw = example_ir()
    return IRHeader.model_validate({k: raw[k] for k in IRHeader.model_fields if k in raw})


def test_a_missing_font_tool_or_package_is_a_persons_to_fix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config(ROOT / "pipeline.toml")
    assert environment.environment_issues(header(), config) == []
    font = header().model_copy(
        update={"typography": header().typography.model_copy(update={"text_font": "No Such Font"})}
    )
    (issue,) = environment.environment_issues(font, config)
    assert (issue.code, issue.path) == ("E-ENVIRONMENT", "typography.text_font")
    monkeypatch.setattr("irpipe.orchestrator.environment.shutil.which", lambda tool: None)
    monkeypatch.setattr("irpipe.orchestrator.environment.importlib.util.find_spec", lambda n: None)
    messages = [i.message for i in environment.environment_issues(header(), config)]
    assert messages[:2] == [
        "latex is not installed; formulas cannot be set",
        "dvisvgm is not installed; formulas cannot be set",
    ]
    assert any(m.startswith("manim is not installed") for m in messages)


# The agent's script


def script(folder: Path, code: str) -> Path:
    folder.mkdir(exist_ok=True)
    (folder / "build_ir.py").write_text(code, encoding="utf-8")
    return folder


def test_a_script_that_writes_ir_json_is_fine(tmp_path: Path) -> None:
    folder = script(tmp_path / "ok", "open('ir.json', 'w').write('{}')\n")
    assert run_script(folder, timeout=60) == []
    assert (folder / "ir.json").read_text() == "{}"


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("raise ValueError('no b vector')\n", "build_ir.py stopped with an error: "),
        ("x = 1\n", "build_ir.py ran but wrote no ir.json"),
        ("import time\ntime.sleep(5)\n", "build_ir.py ran for more than 0.5 s"),
    ],
)
def test_a_script_that_fails_is_the_agents_to_fix(tmp_path: Path, code: str, message: str) -> None:
    (issue,) = run_script(script(tmp_path / "bad", code), timeout=0.5)
    assert (issue.code, str(issue.origin)) == ("E-SCRIPT", "ir")
    assert issue.message.startswith(message)
    if "ValueError" in code:
        assert issue.message.endswith("ValueError: no b vector")


# Coverage


def document(objects: list[dict[str, Any]]) -> IRDocument:
    raw = {k: v for k, v in example_ir().items() if k in IRHeader.model_fields}
    return IRDocument.model_validate({**raw, "objects": objects}, context={"values": {}})


def test_every_must_show_item_needs_an_object_that_covers_it() -> None:
    brief = FrameBrief.model_validate_json((EXAMPLE / "brief.json").read_text(encoding="utf-8"))
    circle = {"id": "c", "type": "circle", "center": [0, 0], "radius": 1}
    covering = [{**circle, "id": f"c{k}", "covers": [i.id]} for k, i in enumerate(brief.must_show)]
    assert coverage_issues(brief, document(covering)) == []
    issues = coverage_issues(brief, document([{**circle, "covers": ["vectors", "shadw"]}]))
    codes = [(i.code, i.path) for i in issues]
    assert codes[0] == ("E-REF", "objects[0].covers[1]")
    assert issues[0].hint == "did you mean 'shadow'?"
    assert [c for c, _ in codes[1:]] == ["W-UNCOVERED"] * 4  # all but "vectors"
    assert issues[1].hint == 'add "covers": ["shadow"] to the object that shows it'


# Routing


def issue(code: str) -> Issue:
    assert E_INTERNAL.code == "E-INTERNAL"  # registered by the run module, imported above
    return ISSUE_CODES.get(code)("x")


@pytest.mark.parametrize(
    ("codes", "to"),
    [
        ([], Destination.DONE),
        (["E-SCHEMA", "W-UNCOVERED"], Destination.AGENT),
        (["E-SCHEMA", "E-BRIEF"], Destination.PLANNER),
        (["E-SCHEMA", "E-BRIEF", "E-ENVIRONMENT"], Destination.HUMAN),
        (["E-CAPABILITY"], Destination.AGENT),
        (["E-INTERNAL"], Destination.HUMAN),
    ],
)
def test_a_person_comes_first_then_the_planner_then_the_agent(
    codes: list[str], to: Destination
) -> None:
    sent = route(Report.build([issue(code) for code in codes]))
    assert sent.to is to
    assert all(i.code in codes for i in sent.issues)


def test_allowed_warnings_go_nowhere() -> None:
    from irpipe.core import Allow

    uncovered = issue("W-UNCOVERED")
    report = Report.build(
        [uncovered], allows=[Allow(code="W-UNCOVERED", reason="shown by the title text")]
    )
    assert route(report).to is Destination.DONE


# Records


def test_alt_text_says_what_the_picture_means_shows_and_writes() -> None:
    brief = FrameBrief.model_validate_json((EXAMPLE / "brief.json").read_text(encoding="utf-8"))
    title = {"id": "t", "type": "text", "text": "Projection of a onto b", "at": [0, 0]}
    vector = {"id": "a", "type": "line", "start": [0, 0], "end": [1, 1], "label": {"tex": "a"}}
    text = alt_text(brief, document([title, vector]))
    lines = text.splitlines()
    assert lines[0] == "The projection of a onto b is the shadow a casts on b."
    assert lines[1].startswith("It shows: a and b drawn from one point, with arrowheads; ")
    assert lines[2:] == ['Words in it: "Projection of a onto b".', "Formulas in it (TeX): a."]
