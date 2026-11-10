"""The repository's pipeline.toml turns the example IR into a picture."""

import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from irpipe.artifacts import IR_SOURCE, LIR, OUT_DIR, RENDERED
from irpipe.core import Pipeline, Report, RunResult, Status, load_config
from irpipe.core.plugins import load_plugins

ROOT = Path(__file__).parent.parent
EXAMPLE = ROOT / "examples" / "projection" / "ir.json"
EXAMPLES = sorted((ROOT / "examples").glob("*/ir.json"))
BACKENDS = {  # backend -> the package it needs and the files it writes
    "manim": ("manim", ["scene.py", "frame.png"]),
    "svg": ("cairosvg", ["frame.svg", "frame.png"]),
}


def run(text: str, out_dir: Path, backend: str | None = None) -> RunResult:
    """The repository's pipeline.toml; ``backend`` draws instead of the one it names."""
    config = load_config(ROOT / "pipeline.toml")
    if backend is None:
        pipeline = Pipeline.from_config(config, inputs=[IR_SOURCE, OUT_DIR])
    else:
        load_plugins(config.pipeline.plugins)
        options = {name: dict(values) for name, values in config.options.items()}
        options["render"] = {**options["render"], "backend": backend}
        stages = config.pipeline.stages
        pipeline = Pipeline.build(stages, inputs=[IR_SOURCE, OUT_DIR], options=options)
    return pipeline.run({IR_SOURCE: text, OUT_DIR: out_dir})


def test_the_configured_backend_is_manim() -> None:
    assert load_config(ROOT / "pipeline.toml").options["render"]["backend"] == "manim"


def test_the_configured_pipeline_runs_the_front_end_then_checks_then_renders() -> None:
    config = load_config(ROOT / "pipeline.toml")
    pipeline = Pipeline.from_config(config, inputs=[IR_SOURCE, OUT_DIR])
    assert pipeline.stage_names == (
        "validate",
        "normalize",
        "measure",
        "place",
        "resolve",
        "check",
        "render",
    )


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("example", EXAMPLES, ids=lambda path: path.parent.name)
def test_every_example_ir_is_ready_and_its_lir_passes_the_published_schema(
    tmp_path: Path, example: Path, backend: str
) -> None:
    package, files = BACKENDS[backend]
    if importlib.util.find_spec(package) is None:
        pytest.skip(f"the {backend} backend needs {package}")
    result = run(example.read_text(encoding="utf-8"), tmp_path, backend)
    report = Report.build(result.issues, stopped_at=result.stopped_at)
    assert report.status is Status.READY, report.issues
    lir = json.loads(result.get(LIR).model_dump_json())
    schema = json.loads((ROOT / "docs" / "spec" / "lir.schema.json").read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(lir)) == []
    rendered = result.get(RENDERED)
    assert [path.name for path in rendered] == files
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted(files)  # nothing else


def test_a_broken_ir_stops_at_validate_and_draws_nothing(tmp_path: Path) -> None:
    result = run(EXAMPLE.read_text(encoding="utf-8")[:-10], tmp_path)
    report = Report.build(result.issues, stopped_at=result.stopped_at)
    assert report.status is Status.STOPPED
    assert [issue.code for issue in report.issues] == ["E-JSON"]
    assert list(tmp_path.iterdir()) == []
