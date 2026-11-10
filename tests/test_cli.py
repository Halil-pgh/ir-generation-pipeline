"""The irpipe command: one ir.json in, a picture and its report out."""

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
    pytest.importorskip("cairosvg")
    status = main(["render", str(EXAMPLE), "-o", str(tmp_path), "--config", str(CONFIG)])
    assert status == 0
    written = sorted(p.name for p in tmp_path.iterdir())
    assert written == ["frame.png", "frame.svg", "lir.json", "report.json"]
    assert capsys.readouterr().out.startswith("READY")
    assert json.loads((tmp_path / "report.json").read_text())["status"] == "READY"


def test_a_broken_ir_prints_its_issues_and_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text(EXAMPLE.read_text().replace('"radius": 0.08', '"raduis": 0.08'))
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
