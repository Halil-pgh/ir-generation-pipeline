"""The example written with irkit: its build_ir.py works its numbers out and writes a valid ir.json.

examples/tangents/build_ir.py is run by the orchestrator, as an agent's
script would be, and the picture must come out READY.
"""

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from irpipe.irkit import Picture
from irpipe.orchestrator.routing import Destination
from irpipe.orchestrator.run import Outcome, orchestrate

ROOT = Path(__file__).parent.parent.parent
EXAMPLE = ROOT / "examples" / "tangents"


def run(out: Path, config: Path) -> Outcome:
    return orchestrate(EXAMPLE / "brief.json", EXAMPLE / "build_ir.py", out, config_path=config)


@pytest.fixture
def svg_config(tmp_path: Path) -> Path:
    """The repository's pipeline.toml, drawing with the SVG backend (fast, no Manim)."""
    text = (ROOT / "pipeline.toml").read_text(encoding="utf-8")
    path = tmp_path / "pipeline.toml"
    path.write_text(text.replace('backend = "manim"', 'backend = "svg"'), encoding="utf-8")
    return path


def by_id(ir: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {obj["id"]: obj for obj in ir["objects"]}


def test_the_example_computes_its_numbers_and_comes_out_ready(
    svg_config: Path, tmp_path: Path
) -> None:
    out = tmp_path / "run"
    outcome = run(out, svg_config)
    assert outcome.report.ready, outcome.report.issues
    assert outcome.route.to is Destination.DONE
    ir = json.loads((out / "ir.json").read_text(encoding="utf-8"))
    objects = by_id(ir)
    # the touching points and the crossing reach the IR exactly, as expressions
    assert objects["T1"]["center"] == ["9/5", "12/5"]
    assert objects["T2"]["center"] == ["9/5", "-12/5"]
    assert objects["M"]["center"] == ["9/5", 0]
    assert objects["t1"]["end"] == ["29/25", "72/25"]  # 6/5 of the way from P to T1
    assert objects["region"]["seed"] == [4, 0]
    assert objects["formula"]["tex"].endswith("= 4")  # the tangent's length, computed
    # the box is the formula as measured, with 0.3 of padding on each side
    formula = Picture.open(out / "header.json").measure_tex(objects["formula"]["tex"])
    box = objects["formula_box"]
    assert (box["width"], box["height"]) == pytest.approx(
        (formula.width + 0.6, formula.height + 0.6)
    )
    assert [i.code for i in outcome.report.issues] == ["W-FILL-OVERLAP"]  # allowed


@pytest.mark.manim
def test_with_manim_the_example_is_ready_too(tmp_path: Path) -> None:
    if importlib.util.find_spec("manim") is None:
        pytest.skip("Manim is not installed")
    outcome = run(tmp_path / "run", ROOT / "pipeline.toml")
    assert outcome.report.ready, outcome.report.issues
    assert (tmp_path / "run" / "scene.py").exists()
