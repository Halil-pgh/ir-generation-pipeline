"""The orchestrator from brief to run folder: what it writes, where it stops, who acts next."""

import importlib.util
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from irpipe.cli import main
from irpipe.core import Pipeline, StageFailedError
from irpipe.orchestrator.routing import Destination
from irpipe.orchestrator.run import Outcome, orchestrate
from irpipe.schema.ir import IRHeader, header_hash

ROOT = Path(__file__).parent.parent.parent
ALL_FILES = [
    "alt.txt", "brief.json", "build_ir.py", "frame.png", "frame.svg", "header.json", "ir.json",
    "lir.json", "meta.json", "report.json",
]  # fmt: skip

type Example = Callable[..., Path]


def go(source: Path, out: Path, config: Path, script: str | None = None) -> Outcome:
    if script is not None:
        (source / "build_ir.py").write_text(script, encoding="utf-8")
    return orchestrate(source / "brief.json", source / "build_ir.py", out, config_path=config)


def names(folder: Path) -> list[str]:
    return sorted(path.name for path in folder.iterdir())


def test_a_ready_run_fills_the_whole_folder(
    example: Example, svg_config: Path, tmp_path: Path
) -> None:
    out = tmp_path / "run"
    outcome = go(example(), out, svg_config)
    assert outcome.report.ready, outcome.report.issues
    assert outcome.route.to is Destination.DONE
    assert names(out) == ALL_FILES  # SVG draws frame.png itself; no scene.py
    header = IRHeader.model_validate_json((out / "header.json").read_text(encoding="utf-8"))
    ir = json.loads((out / "ir.json").read_text(encoding="utf-8"))
    assert IRHeader.model_validate({k: ir[k] for k in IRHeader.model_fields if k in ir}) == header
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["ir"]["header_hash"] == header_hash(header)
    assert meta["pipeline"]["stages"][:2] == ["validate", "check_header"]
    assert meta["status"] == "READY"
    assert (out / "alt.txt").read_text().startswith("The projection of a onto b is the shadow")


def test_an_agent_that_changes_the_header_is_told_to_put_it_back(
    example: Example, svg_config: Path, tmp_path: Path
) -> None:
    source = example()
    script = (source / "build_ir.py").read_text(encoding="utf-8")
    reading = 'header = json.loads(Path("header.json").read_text(encoding="utf-8"))'
    script = script.replace(reading, reading + '\nheader["intent"] = "something else"')
    outcome = go(source, tmp_path / "run", svg_config, script)
    assert [i.code for i in outcome.route.issues] == ["E-HEADER"]
    assert outcome.route.to is Destination.AGENT
    assert (tmp_path / "run" / "frame.png").exists()  # the picture is still drawn


def test_a_script_that_fails_stops_the_run_and_goes_to_the_agent(
    example: Example, svg_config: Path, tmp_path: Path
) -> None:
    out = tmp_path / "run"
    outcome = go(example(), out, svg_config, "raise RuntimeError('oops')\n")
    assert (outcome.report.stopped_at, outcome.route.to) == ("script", Destination.AGENT)
    assert [i.code for i in outcome.report.issues] == ["E-SCRIPT"]
    assert names(out) == ["brief.json", "build_ir.py", "header.json", "meta.json", "report.json"]


def test_a_broken_brief_stops_the_run_and_goes_to_the_planner(
    example: Example, svg_config: Path, tmp_path: Path
) -> None:
    out = tmp_path / "run"
    outcome = go(example(focus=["nothing"]), out, svg_config)
    assert (outcome.report.stopped_at, outcome.route.to) == ("brief", Destination.PLANNER)
    assert names(out) == ["brief.json", "build_ir.py", "report.json"]


def test_a_missing_tool_stops_the_run_before_the_script(
    example: Example, svg_config: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("irpipe.orchestrator.environment.shutil.which", lambda tool: None)
    outcome = go(example(), tmp_path / "run", svg_config)
    assert (outcome.report.stopped_at, outcome.route.to) == ("environment", Destination.HUMAN)
    assert not (tmp_path / "run" / "ir.json").exists()


def test_a_stage_that_crashes_is_a_fault_to_report(
    example: Example, svg_config: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def crash(self: Pipeline, inputs: Any) -> Any:
        raise StageFailedError("place", ZeroDivisionError("division by zero"))

    monkeypatch.setattr(Pipeline, "run", crash)
    outcome = go(example(), tmp_path / "run", svg_config)
    (issue,) = outcome.report.issues
    assert (issue.code, issue.message) == (
        "E-INTERNAL",
        "stage 'place' failed: ZeroDivisionError: division by zero",
    )
    assert (outcome.report.stopped_at, outcome.route.to) == ("place", Destination.HUMAN)


def test_files_of_an_earlier_run_are_not_left_behind(
    example: Example, svg_config: Path, tmp_path: Path
) -> None:
    out = tmp_path / "run"
    out.mkdir()
    (out / "frame.png").write_text("old")
    (out / "notes.txt").write_text("mine")
    go(example(focus=["nothing"]), out, svg_config)
    assert names(out) == ["brief.json", "build_ir.py", "notes.txt", "report.json"]


def test_an_uncovered_item_is_for_the_agent_and_allow_accepts_it(
    example: Example, svg_config: Path, tmp_path: Path
) -> None:
    source = example()
    script = (
        (source / "build_ir.py").read_text(encoding="utf-8").replace(', "covers": ["angle"]', "")
    )
    outcome = go(source, tmp_path / "run", svg_config, script)
    assert [i.code for i in outcome.route.issues] == ["W-UNCOVERED"]
    allow = '{"code": "W-UNCOVERED", "reason": "the angle is in the formula already"}'
    script = script.replace(
        '    "objects": objects,\n', f'    "objects": objects,\n    "allow": [{allow}],\n'
    )
    assert go(source, tmp_path / "run", svg_config, script).report.ready


def test_the_command_names_the_folder_after_the_brief_and_says_who_is_next(
    example: Example,
    svg_config: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = example()
    monkeypatch.chdir(tmp_path)
    status = main(
        [
            "run",
            str(source / "brief.json"),
            str(source / "build_ir.py"),
            "--config",
            str(svg_config),
        ]
    )
    assert status == 0
    assert (tmp_path / "runs" / "projection" / "frame.png").exists()
    printed = capsys.readouterr().out
    assert printed.startswith("READY") and printed.rstrip().endswith(
        "next: done: the picture is ready"
    )
    assert main(["run", str(source / "brief.json"), str(tmp_path / "nope.py")]) == 2


@pytest.mark.manim
def test_with_manim_the_folder_holds_scene_py_and_the_svg_reference(
    example: Example, tmp_path: Path
) -> None:
    if importlib.util.find_spec("manim") is None:
        pytest.skip("Manim is not installed")
    out = tmp_path / "run"
    outcome = go(example(), out, ROOT / "pipeline.toml")
    assert outcome.report.ready, outcome.report.issues
    assert names(out) == sorted([*ALL_FILES, "scene.py"])
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert (meta["backend"]["name"], meta["reference"]) == ("manim", "svg")
