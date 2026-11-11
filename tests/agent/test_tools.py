"""The agent's tools over a workspace: the script, validate, measuring, resolve and check."""

from collections.abc import Callable
from pathlib import Path

import pytest

from irpipe.agent import AgentSettings
from irpipe.agent.sandbox import Sandbox
from irpipe.agent.tools import Tools
from irpipe.core import load_config
from irpipe.orchestrator.inputs import read_inputs

ROOT = Path(__file__).parent.parent.parent
EXAMPLE = ROOT / "examples" / "tangents"
SCRIPT = (EXAMPLE / "build_ir.py").read_text(encoding="utf-8")


@pytest.fixture
def tools(tmp_path: Path, agent_config: Callable[..., Path]) -> Tools:
    inputs, issues = read_inputs(EXAMPLE / "brief.json")
    assert inputs is not None, issues
    config = load_config(agent_config())
    return Tools(tmp_path / "work", inputs, config, AgentSettings(), Sandbox("audit"))


def test_run_python_runs_the_script_and_validates_what_it_wrote(tools: Tools) -> None:
    result = tools.run_python(SCRIPT)
    assert result.startswith("build_ir.py ran in ") and "wrote ir.json (18 objects)" in result
    assert result.endswith("validate: no problems.")
    assert (tools.folder / "header.json").exists() and tools.has_ir()


def test_a_failing_script_comes_back_with_its_own_traceback(tools: Tools) -> None:
    result = tools.run_python("x = 1\nraise ValueError('no b vector')\n")
    assert result.startswith("build_ir.py stopped with an error (exit 1):\nTraceback")
    assert 'File "build_ir.py", line 2, in <module>' in result and "jail.py" not in result
    assert result.endswith("ValueError: no b vector")
    assert "wrote no ir.json: end with pic.write()" in tools.run_python("print('hi')\n")
    assert "It printed:\nhi" in tools.run_python("print('hi')\n")


def test_validate_and_check_say_what_is_wrong_with_paths_and_hints(tools: Tools) -> None:
    script = SCRIPT.replace('covers=["chord"]', 'covers=["chord"], dash=[-1]')
    result = tools.run_python(script)
    assert "validate: 1 error, 0 warnings" in result and "E-SCHEMA objects[3].dash[0]" in result
    tools.run_python(SCRIPT.replace(', covers=["region"]', ""))
    checked = tools.check()
    assert checked.startswith("0 errors, 1 warning, 1 allowed")
    assert "- W-UNCOVERED: must_show 'region'" in checked
    assert "W-FILL-OVERLAP" in checked and "allowed: P's dot sits on the tip" in checked


def test_resolve_lists_where_every_object_landed(tools: Tools) -> None:
    tools.run_python(SCRIPT)
    lines = tools.resolve().splitlines()
    assert lines[0].startswith("frame: [-8, -4.5, 8, 4.5]; safe area: [-7.60, -4.10, 7.60, 4.10]")
    title = next(line for line in lines if line.startswith("title (text): ["))
    left, _, right, top = (float(v) for v in title.split("[")[1].rstrip("]").split(", "))
    assert left == pytest.approx(-right, abs=0.01) and top == pytest.approx(4.10, abs=0.01)
    assert any(line.startswith("T1.label (math): [") for line in lines)


def test_measuring_answers_in_frame_units_or_says_what_is_wrong(tools: Tools) -> None:
    assert tools.measure_text('{"text": "abc", "size": "heading"}').startswith("width ")
    assert tools.measure_tex('{"tex": "x^2"}').endswith("in frame units")
    assert tools.measure_tex('{"tex": "\\\\frac{a}"}').startswith("E-TEX: LaTeX cannot set it")
    assert tools.measure_text("{nope").startswith("the body must be a JSON object")
    assert (
        tools.measure_text('{"txt": "a"}')
        == "unknown argument 'txt'; it takes: italic, size, text, weight"
    )
    assert tools.measure_text('{"text": "a", "size": "huge"}').startswith("cannot measure")
