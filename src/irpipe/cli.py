"""The ``irpipe`` command: turn one ir.json into a picture.

    irpipe render examples/projection/ir.json          # into runs/projection/
    irpipe render my/ir.json -o out/ --config pipeline.toml

It runs the stages ``pipeline.toml`` lists, so the result is exactly what the
pipeline makes. Next to the backend's files it writes lir.json and
report.json, then prints the report. The exit status is 0 when the picture
is READY, 1 when it is not, 2 when the command itself could not run.

The orchestrator (step 19) will write the full run folder; until then this
is the way to try an IR by hand.
"""

import argparse
import sys
from pathlib import Path

from irpipe.artifacts import IR, IR_SOURCE, LIR, OUT_DIR, RENDERED
from irpipe.core import Pipeline, PipelineError, Report, RunResult, load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="irpipe", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    render = commands.add_parser("render", help="compile an ir.json and draw it")
    render.add_argument("ir", type=Path, help="the ir.json to draw")
    render.add_argument("-o", "--out", type=Path, help="output folder (default: runs/<name>)")
    render.add_argument(
        "--config", type=Path, default=Path("pipeline.toml"), help="pipeline file to run"
    )
    args = parser.parse_args(argv)
    try:
        return render_ir(args.ir, args.out or default_out(args.ir), args.config)
    except (OSError, PipelineError) as exc:
        print(f"irpipe: {exc}", file=sys.stderr)
        return 2


def default_out(ir_path: Path) -> Path:
    """runs/<folder> for a file named ir.json, runs/<file name> otherwise."""
    name = (
        ir_path.parent.name if ir_path.name == "ir.json" and ir_path.parent.name else ir_path.stem
    )
    return Path("runs") / name


def render_ir(ir_path: Path, out_dir: Path, config_path: Path) -> int:
    pipeline = Pipeline.from_config(load_config(config_path), inputs=[IR_SOURCE, OUT_DIR])
    result = pipeline.run({IR_SOURCE: ir_path.read_text(encoding="utf-8"), OUT_DIR: out_dir})
    report = _report(result)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    if RENDERED.name in result.artifacts:
        rendered = result.get(RENDERED)
        written.extend(rendered)
    if LIR.name in result.artifacts:
        lir_file = out_dir / "lir.json"
        lir_file.write_text(result.get(LIR).model_dump_json(indent=2) + "\n", encoding="utf-8")
        written.append(lir_file)
    report_file = out_dir / "report.json"
    report_file.write_text(
        report.model_dump_json(indent=2, exclude_none=True) + "\n", encoding="utf-8"
    )
    written.append(report_file)

    print(report.headline)
    for issue in report.issues:
        where = f" {issue.path}" if issue.path else ""
        mark = " (allowed)" if not issue.is_open else ""
        print(f"  {issue.code}{where}: {issue.message}{mark}")
        if issue.hint:
            print(f"      hint: {issue.hint}")
    for path in written:
        print(f"  -> {path}")
    return 0 if report.ready else 1


def _report(result: RunResult) -> Report:
    """The run's report, with the IR's allow entries applied when there is an IR."""
    allows = result.get(IR).allow if IR.name in result.artifacts else ()
    return Report.build(result.issues, allows=allows, stopped_at=result.stopped_at)


if __name__ == "__main__":
    raise SystemExit(main())
