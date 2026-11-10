"""The repository's pipeline.toml compiles the example IR into a valid LIR."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from irpipe.artifacts import IR_SOURCE, LIR
from irpipe.core import Pipeline, Report, Status, load_config

ROOT = Path(__file__).parent.parent
EXAMPLE = ROOT / "examples" / "projection" / "ir.json"


def pipeline() -> Pipeline:
    return Pipeline.from_config(load_config(ROOT / "pipeline.toml"), inputs=[IR_SOURCE])


def test_the_configured_pipeline_is_validate_then_resolve() -> None:
    assert pipeline().stage_names == ("validate", "resolve")


def test_the_example_ir_is_ready_and_its_lir_passes_the_published_schema() -> None:
    result = pipeline().run({IR_SOURCE: EXAMPLE.read_text(encoding="utf-8")})
    report = Report.build(result.issues, stopped_at=result.stopped_at)
    assert report.status is Status.READY, report.issues
    lir = json.loads(result.get(LIR).model_dump_json())
    schema = json.loads((ROOT / "docs" / "spec" / "lir.schema.json").read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(lir)) == []


def test_a_broken_ir_stops_at_validate() -> None:
    result = pipeline().run({IR_SOURCE: EXAMPLE.read_text(encoding="utf-8")[:-10]})
    report = Report.build(result.issues, stopped_at=result.stopped_at)
    assert report.status is Status.STOPPED
    assert [issue.code for issue in report.issues] == ["E-JSON"]
