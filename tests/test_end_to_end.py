"""The repository's pipeline.toml turns the example IR into a picture."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from irpipe.artifacts import IR_SOURCE, LIR, OUT_DIR, RENDERED
from irpipe.core import Pipeline, Report, RunResult, Status, load_config

ROOT = Path(__file__).parent.parent
EXAMPLE = ROOT / "examples" / "projection" / "ir.json"


def run(text: str, out_dir: Path) -> RunResult:
    config = load_config(ROOT / "pipeline.toml")
    pipeline = Pipeline.from_config(config, inputs=[IR_SOURCE, OUT_DIR])
    return pipeline.run({IR_SOURCE: text, OUT_DIR: out_dir})


def test_the_configured_pipeline_is_validate_resolve_render() -> None:
    config = load_config(ROOT / "pipeline.toml")
    pipeline = Pipeline.from_config(config, inputs=[IR_SOURCE, OUT_DIR])
    assert pipeline.stage_names == ("validate", "resolve", "render")


def test_the_example_ir_is_ready_and_its_lir_passes_the_published_schema(
    tmp_path: Path,
) -> None:
    pytest.importorskip("cairosvg")
    result = run(EXAMPLE.read_text(encoding="utf-8"), tmp_path)
    report = Report.build(result.issues, stopped_at=result.stopped_at)
    assert report.status is Status.READY, report.issues
    lir = json.loads(result.get(LIR).model_dump_json())
    schema = json.loads((ROOT / "docs" / "spec" / "lir.schema.json").read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(lir)) == []
    rendered = result.get(RENDERED)
    assert [path.name for path in rendered] == ["frame.svg", "frame.png"]


def test_a_broken_ir_stops_at_validate_and_draws_nothing(tmp_path: Path) -> None:
    result = run(EXAMPLE.read_text(encoding="utf-8")[:-10], tmp_path)
    report = Report.build(result.issues, stopped_at=result.stopped_at)
    assert report.status is Status.STOPPED
    assert [issue.code for issue in report.issues] == ["E-JSON"]
    assert list(tmp_path.iterdir()) == []
