"""One frame, from the planner's brief to the run folder (analysis §1).

    outcome = orchestrate(Path("brief.json"), Path("build_ir.py"), Path("runs/projection"))
    outcome.report.status, outcome.route.to, outcome.files

In order, stopping at the first step that cannot go on:

1. read the brief (and its lesson), work out the frame's style and lock
   the header (E-BRIEF: back to the planner);
2. check that the tools this picture needs are installed (E-ENVIRONMENT);
3. run the agent's build_ir.py, which reads header.json and writes
   ir.json (E-SCRIPT);
4. run pipeline.toml's stages, with check_header after validate, so a
   changed header is an E-HEADER; a stage that crashes is E-INTERNAL;
5. when the picture is drawn by another backend, draw the SVG reference
   too (frame.svg);
6. check the brief's must_show items are covered (W-UNCOVERED);
7. write report.json, meta.json and alt.txt, and say who acts next.

The run folder then holds brief.json, build_ir.py, header.json, ir.json,
lir.json, the backend's files (scene.py and frame.png for Manim), the SVG
reference frame.svg, report.json, meta.json and alt.txt.
"""

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from irpipe.artifacts import IR, IR_SOURCE, LIR, LOCKED_HEADER, OUT_DIR
from irpipe.backends.render import Render
from irpipe.core import (
    ISSUE_CODES,
    Issue,
    IssueCode,
    Origin,
    Pipeline,
    PipelineConfig,
    Report,
    RunResult,
    StageFailedError,
    StageRun,
    load_config,
)
from irpipe.core.plugins import load_plugins
from irpipe.orchestrator.coverage import coverage_issues
from irpipe.orchestrator.environment import environment_issues
from irpipe.orchestrator.inputs import Inputs, read_inputs
from irpipe.orchestrator.records import alt_text, meta_record
from irpipe.orchestrator.routing import Route, route
from irpipe.orchestrator.script import HEADER, SCRIPT, run_script
from irpipe.orchestrator.script import IR as IR_FILE
from irpipe.schema.ir import IRDocument

E_INTERNAL = ISSUE_CODES.register(
    IssueCode("E-INTERNAL", Origin.INTERNAL, "a stage of the compiler crashed: a fault to report")
)

OUTPUTS: Final = (
    "brief.json", SCRIPT, HEADER, IR_FILE, "lir.json", "scene.py", "frame.png", "frame.svg",
    "report.json", "meta.json", "alt.txt",
)  # fmt: skip
"""The files a run writes; left over from an earlier run, they are removed first."""

SCRIPT_TIMEOUT: Final = 120.0


@dataclass(frozen=True)
class Outcome:
    folder: Path
    report: Report
    route: Route
    files: tuple[Path, ...]


def orchestrate(
    brief_path: Path,
    script_path: Path,
    folder: Path,
    *,
    lesson_path: Path | None = None,
    config_path: Path = Path("pipeline.toml"),
    script_timeout: float = SCRIPT_TIMEOUT,
) -> Outcome:
    """Draw the frame ``brief_path`` describes with the agent's ``script_path`` into ``folder``."""
    started, clock = datetime.now(UTC).isoformat(timespec="seconds"), time.perf_counter()
    folder.mkdir(parents=True, exist_ok=True)
    for name in OUTPUTS:
        (folder / name).unlink(missing_ok=True)
    (folder / "brief.json").write_text(brief_path.read_text(encoding="utf-8"), encoding="utf-8")
    (folder / SCRIPT).write_text(script_path.read_text(encoding="utf-8"), encoding="utf-8")
    config = load_config(config_path)
    run = _Run(folder, config, started, clock)

    inputs, issues = read_inputs(brief_path, lesson_path)
    if inputs is None:
        return run.finish(issues, stopped_at="brief")
    run.inputs = inputs
    header_text = inputs.header.model_dump_json(indent=2, exclude_none=True)
    (folder / HEADER).write_text(header_text + "\n", encoding="utf-8")
    issues = environment_issues(inputs.header, config)
    if issues:
        return run.finish(issues, stopped_at="environment")
    issues = run_script(folder, script_timeout)
    if issues:
        return run.finish(issues, stopped_at="script")

    result = run.pipeline((folder / IR_FILE).read_text(encoding="utf-8"))
    if result is None:
        return run.finish(run.crash, stopped_at=run.crash_stage)
    issues = list(result.issues)
    if LIR.name in result.artifacts:
        lir = result.get(LIR)
        (folder / "lir.json").write_text(lir.model_dump_json(indent=2) + "\n", encoding="utf-8")
        issues += run.reference(result)
    if IR.name in result.artifacts:
        run.document = result.get(IR)
        issues += coverage_issues(inputs.brief, run.document)
    return run.finish(issues, stopped_at=result.stopped_at, stages=result.stages)


class _Run:
    """The state of one run while it goes, and how it is written down at the end."""

    def __init__(self, folder: Path, config: PipelineConfig, started: str, clock: float) -> None:
        self.folder = folder
        self.config = config
        self.started = started
        self.clock = clock
        self.inputs: Inputs | None = None
        self.document: IRDocument | None = None
        self.crash: list[Issue] = []
        self.crash_stage: str | None = None

    def pipeline(self, ir_text: str) -> RunResult | None:
        """pipeline.toml's stages, with check_header after validate; None if one crashed."""
        assert self.inputs is not None
        load_plugins(self.config.pipeline.plugins)
        stages = list(self.config.pipeline.stages)
        if "validate" in stages and "check_header" not in stages:
            stages.insert(stages.index("validate") + 1, "check_header")
        inputs: dict[Any, object] = {
            IR_SOURCE: ir_text,
            OUT_DIR: self.folder,
            LOCKED_HEADER: self.inputs.header,
        }
        pipeline = Pipeline.build(stages, inputs=list(inputs), options=self.config.options)
        try:
            return pipeline.run(inputs)
        except StageFailedError as error:  # its message names the stage and the exception
            self.crash = [E_INTERNAL(str(error), hint="a fault in the compiler; report it")]
            self.crash_stage = error.stage
            return None

    def reference(self, result: RunResult) -> list[Issue]:
        """frame.svg, the SVG reference, when another backend drew the picture."""
        if self.config.options.get("render", {}).get("backend", "svg") == "svg":
            return []
        options = {"render": {"backend": "svg", "svg": {"png": False}}}
        svg = Pipeline([Render()], inputs=[LIR, OUT_DIR], options=options)
        return list(svg.run({LIR: result.get(LIR), OUT_DIR: self.folder}).issues)

    def finish(
        self,
        issues: list[Issue],
        stopped_at: str | None,
        stages: tuple[StageRun, ...] = (),
    ) -> Outcome:
        allows = self.document.allow if self.document is not None else ()
        report = Report.build(issues, allows=allows, stopped_at=stopped_at)
        report_text = report.model_dump_json(indent=2, exclude_none=True)
        (self.folder / "report.json").write_text(report_text + "\n", encoding="utf-8")
        if self.inputs is not None:
            seconds = time.perf_counter() - self.clock
            meta = meta_record(
                self.inputs.brief,
                self.inputs.header,
                self.config,
                stages,
                status=str(report.status),
                started=self.started,
                seconds=seconds,
            )
            meta_text = json.dumps(meta, indent=2, ensure_ascii=False)
            (self.folder / "meta.json").write_text(meta_text + "\n", encoding="utf-8")
            if self.document is not None:
                text = alt_text(self.inputs.brief, self.document)
                (self.folder / "alt.txt").write_text(text, encoding="utf-8")
        files = tuple(self.folder / name for name in OUTPUTS if (self.folder / name).exists())
        return Outcome(self.folder, report, route(report), files)
