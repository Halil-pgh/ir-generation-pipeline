"""The irpipe command: one ir.json in, a picture and its report out."""

import importlib.util
import json
from pathlib import Path

import pytest

from irpipe.cli import default_out, main

ROOT = Path(__file__).parent.parent
EXAMPLE = ROOT / "examples" / "projection" / "ir.json"
CONFIG = ROOT / "pipeline.toml"


def test_the_example_renders_and_the_command_says_ready(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    if importlib.util.find_spec("manim") is None:
        pytest.skip("pipeline.toml draws with Manim, which is not installed")
    status = main(["render", str(EXAMPLE), "-o", str(tmp_path), "--config", str(CONFIG)])
    assert status == 0
    written = sorted(p.name for p in tmp_path.iterdir())
    assert written == ["frame.png", "lir.json", "report.json", "scene.py"]
    assert capsys.readouterr().out.startswith("READY")
    assert json.loads((tmp_path / "report.json").read_text())["status"] == "READY"


def test_a_broken_ir_prints_its_issues_and_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = json.loads(EXAMPLE.read_text())
    circle = next(obj for obj in data["objects"] if obj["type"] == "circle")
    circle["raduis"] = circle.pop("radius")
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps(data))
    out = tmp_path / "out"
    status = main(["render", str(broken), "-o", str(out), "--config", str(CONFIG)])
    assert status == 1
    printed = capsys.readouterr().out
    assert "STOPPED at 'validate'" in printed
    assert "unknown field 'raduis'" in printed
    assert "hint: did you mean 'radius'?" in printed
    assert sorted(p.name for p in out.iterdir()) == ["report.json"]


def test_a_missing_file_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["render", str(tmp_path / "nope.json"), "--config", str(CONFIG)]) == 2
    assert "irpipe:" in capsys.readouterr().err


def test_the_default_output_folder_is_named_after_the_example() -> None:
    assert default_out(Path("examples/projection/ir.json")) == Path("runs/projection")
    assert default_out(Path("drafts/parabola.json")) == Path("runs/parabola")
