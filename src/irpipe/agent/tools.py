"""The agent's tools (analysis §4), run in its workspace; each answers in text for the model.

    tools = Tools(work_folder, inputs, config, settings)
    tools.run_python(script)        # writes build_ir.py, runs it in the sandbox, validates
    tools.validate()                # schema, names, references, the header
    tools.measure_text('{"text": "Hi", "size": "heading"}')
    tools.measure_tex('{"tex": "\\\\frac{a}{b}"}')
    tools.resolve()                 # where every object landed: its box in frame units
    tools.check()                   # validate, layout, the picture's checks, coverage
    tools.ask_planner('{"request": "split", "reason": "..."}')   # back to the planner

None of them draws the picture or runs Manim: they are the front-end's
stages over the workspace's ir.json, with pipeline.toml's settings and the
locked header (check_header runs after validate). Problems come back as
issues in IR terms: code, JSON path, objects, hint. ``submit`` belongs to
the session (session.py), which compiles and draws a turn. ``ask_planner``
turns the agent's request into a PlannerRequest; the session then ends and
the frame goes back to the planner (step 22).
"""

import json
from pathlib import Path
from typing import Any

from irpipe.agent.sandbox import Sandbox, sandbox_for
from irpipe.agent.settings import AgentSettings
from irpipe.artifacts import IR, IR_NORMAL, IR_SOURCE, LIR, LOCKED_HEADER
from irpipe.checks.picture import Picture, reach_of
from irpipe.core import (
    Issue,
    Pipeline,
    PipelineConfig,
    Report,
    RunResult,
    Severity,
    StageFailedError,
)
from irpipe.core.plugins import load_plugins
from irpipe.irkit.measure import DEFAULT_PROVIDER, Measurer
from irpipe.metrics import MissingToolError, TexError
from irpipe.orchestrator.coverage import coverage_issues
from irpipe.orchestrator.inputs import Inputs
from irpipe.orchestrator.run import E_INTERNAL
from irpipe.orchestrator.script import HEADER, SCRIPT
from irpipe.orchestrator.script import IR as IR_FILE
from irpipe.schema.request import PlannerRequest

NAMES = (
    "run_python", "validate", "measure_text", "measure_tex", "resolve", "check", "submit",
    "ask_planner",
)  # fmt: skip
"""Every tool the model may call."""
STDOUT_LINES = 40
TRACEBACK_LINES = 15


class Tools:
    """The tools, over one workspace folder holding header.json, build_ir.py and ir.json."""

    def __init__(
        self,
        folder: Path,
        inputs: Inputs,
        config: PipelineConfig,
        settings: AgentSettings,
        sandbox: Sandbox | None = None,
    ) -> None:
        self.folder = folder
        self.inputs = inputs
        self.config = config
        self.settings = settings
        self.sandbox = sandbox or sandbox_for(settings.sandbox, settings.memory_mb)
        folder.mkdir(parents=True, exist_ok=True)
        header = inputs.header.model_dump_json(indent=2, exclude_none=True)
        (folder / HEADER).write_text(header + "\n", encoding="utf-8")
        provider = str(config.options.get("measure", {}).get("metrics", DEFAULT_PROVIDER))
        self.measurer = Measurer(inputs.header, provider)
        load_plugins(config.pipeline.plugins)

    # The script

    def run_python(self, script: str) -> str:
        """Replace build_ir.py with ``script``, run it in the sandbox, validate what it wrote."""
        (self.folder / SCRIPT).write_text(script.rstrip() + "\n", encoding="utf-8")
        (self.folder / IR_FILE).unlink(missing_ok=True)
        ran = self.sandbox.run(self.folder, self.settings.script_timeout)
        printed = _tail(ran.stdout, STDOUT_LINES)
        said = f"\nIt printed:\n{printed}" if printed else ""
        if ran.timed_out:
            return f"{SCRIPT} ran for more than {self.settings.script_timeout:g} s and was stopped."
        if ran.returncode != 0:
            trace = _tail(ran.stderr, TRACEBACK_LINES)
            return f"{SCRIPT} stopped with an error (exit {ran.returncode}):\n{trace}{said}"
        took = f"{SCRIPT} ran in {ran.seconds:.1f} s"
        if not self.has_ir():
            return f"{took} but wrote no {IR_FILE}: end with pic.write().{said}"
        wrote = f"{took} and wrote {IR_FILE} ({self._counts()}).{said}"
        return f"{wrote}\n\nvalidate: {self.validate()}"

    def has_script(self) -> bool:
        return (self.folder / SCRIPT).exists()

    def has_ir(self) -> bool:
        return (self.folder / IR_FILE).exists()

    # The front-end's answers

    def validate_issues(self) -> list[Issue]:
        """What validate and check_header say about the current ir.json."""
        found = self._front_end("validate")
        return list(found.issues) if isinstance(found, RunResult) else [found]

    def validate(self) -> str:
        if not (self.folder / IR_FILE).exists():
            return f"there is no {IR_FILE} yet: run build_ir.py with run_python"
        return describe(self.validate_issues())

    def resolve(self) -> str:
        """Where every object landed, as the boxes it reaches (strokes included)."""
        found = self._front_end("resolve")
        if not isinstance(found, RunResult):
            return describe([found])
        if LIR.name not in found.artifacts:
            return "the picture could not be laid out:\n" + describe(list(found.issues))
        document = found.get(IR_NORMAL)
        types = {obj.id: obj.type for obj in document.objects}
        frame, safe = document.frame.units, document.frame.safe
        lines = [
            f"frame: [{-frame[0] / 2:g}, {-frame[1] / 2:g}, {frame[0] / 2:g}, {frame[1] / 2:g}]; "
            f"safe area: {_box(safe)} (frame units; [left, bottom, right, top])",
            "",
        ]
        for owner, drawn in Picture(found.get(LIR), document).by_owner().items():
            kind = types.get(owner, "label" if owner.endswith(".label") else "part")
            lines.append(f"{owner} ({kind}): {_box(reach_of(drawn))}")
        problems = [i for i in _judged(found, list(found.issues)) if i.is_open]
        if problems:
            lines += ["", "problems so far:", describe(problems)]
        return "\n".join(lines)

    def check(self) -> str:
        """Every issue a submission would get before drawing: front-end, checks, coverage."""
        found = self._front_end("check")
        if not isinstance(found, RunResult):
            return describe([found])
        issues = list(found.issues)
        if IR.name in found.artifacts:
            issues += coverage_issues(self.inputs.brief, found.get(IR))
        issues = _judged(found, issues)
        if found.stopped_at is not None:
            return f"stopped at {found.stopped_at}:\n" + describe(issues)
        return describe(issues)

    # Measuring

    def measure_text(self, body: str) -> str:
        args = _arguments(body, {"text", "size", "weight", "italic"}, "text")
        if isinstance(args, str):
            return args
        try:
            box = self.measurer.text(
                str(args["text"]), args.get("size", "body"), args.get("weight", "regular"),
                bool(args.get("italic", False)),
            )  # fmt: skip
        except (MissingToolError, AttributeError, ValueError) as error:
            return f"cannot measure: {error}"
        return _size(box.width, box.ascent, box.descent)

    def measure_tex(self, body: str) -> str:
        args = _arguments(body, {"tex", "size"}, "tex")
        if isinstance(args, str):
            return args
        try:
            box = self.measurer.tex(str(args["tex"]), args.get("size", "body"))
        except TexError as error:
            return f"E-TEX: LaTeX cannot set it: {error}"
        except (MissingToolError, AttributeError, ValueError) as error:
            return f"cannot measure: {error}"
        return _size(box.width, box.ascent, box.descent)

    # The way back to the planner

    def ask_planner(self, body: str) -> PlannerRequest | str:
        """The agent's request to change the brief, or what is wrong with it.

        BODY ``{"request": "shorten" | "split", "reason": "...", "items": [...]}``.
        """
        args = _arguments(body, {"request", "reason", "items"}, "request")
        if isinstance(args, str):
            return args
        kind = args["request"]
        if kind not in ("shorten", "split"):
            return f'request is "shorten" or "split", not {json.dumps(kind)}'
        reason = str(args.get("reason", "")).strip()
        if not reason:
            return "'reason' is required: say what does not fit, and where"
        items = args.get("items", [])
        if not isinstance(items, list) or not all(isinstance(i, str) and i for i in items):
            return "'items' is a list of the must_show ids or texts that do not fit"
        return PlannerRequest(
            frame=self.inputs.brief.id, kind=kind, reason=reason, items=tuple(items)
        )

    # Running the front-end

    def _front_end(self, last: str) -> RunResult | Issue:
        """pipeline.toml's stages up to ``last`` (no render), with check_header after validate."""
        stages = [s for s in self.config.pipeline.stages if s != "render"]
        if last in stages:
            stages = stages[: stages.index(last) + 1]
        if "validate" in stages:
            stages.insert(stages.index("validate") + 1, "check_header")
        text = (self.folder / IR_FILE).read_text(encoding="utf-8")
        inputs: dict[Any, object] = {IR_SOURCE: text, LOCKED_HEADER: self.inputs.header}
        try:
            pipeline = Pipeline.build(stages, inputs=list(inputs), options=self.config.options)
            return pipeline.run(inputs)
        except StageFailedError as error:
            return E_INTERNAL(str(error), hint="a fault in the compiler, not in your script")

    def _counts(self) -> str:
        try:
            data = json.loads((self.folder / IR_FILE).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return "not JSON"
        objects, defs = len(data.get("objects", ())), len(data.get("defs", ()))
        return f"{objects} objects" + (f", {defs} defs" if defs else "")


def _judged(found: RunResult, issues: list[Issue]) -> list[Issue]:
    """``issues`` with the IR's allow entries applied, as the report will apply them."""
    allows = found.get(IR).allow if IR.name in found.artifacts else ()
    return list(Report.build(issues, allows=allows).issues)


def describe(issues: list[Issue]) -> str:
    """Issues as the model reads them: counts, then one line each (and its hint)."""
    if not issues:
        return "no problems."
    open_ = [i for i in issues if i.is_open]
    errors = sum(i.severity is Severity.ERROR for i in open_)
    warnings = len(open_) - errors
    head = f"{errors} error{'s' * (errors != 1)}, {warnings} warning{'s' * (warnings != 1)}"
    allowed = len(issues) - len(open_)
    lines = [head + (f", {allowed} allowed" if allowed else "")]
    for issue in issues:
        where = f" {issue.path}" if issue.path else ""
        about = f" [{', '.join(issue.objects)}]" if issue.objects else ""
        lines.append(f"- {issue.code}{where}{about}: {issue.message}")
        if issue.allowed_because:
            lines.append(f"    allowed: {issue.allowed_because}")
        elif issue.hint:
            lines.append(f"    hint: {issue.hint}")
    return "\n".join(lines)


def _arguments(body: str, known: set[str], required: str) -> dict[str, Any] | str:
    try:
        args = json.loads(body or "{}")
    except json.JSONDecodeError as error:
        return f"the body must be a JSON object: {error}"
    if not isinstance(args, dict):
        return "the body must be a JSON object"
    unknown = set(args) - known
    if unknown:
        return f"unknown argument {sorted(unknown)[0]!r}; it takes: {', '.join(sorted(known))}"
    if required not in args:
        return f"{required!r} is required"
    return args


def _size(width: float, ascent: float, descent: float) -> str:
    return (
        f"width {width:.3f}, height {ascent + descent:.3f} (ascent {ascent:.3f} above the "
        f"baseline, descent {descent:.3f} below), in frame units"
    )


def _box(box: tuple[float, float, float, float] | Any) -> str:
    return "[" + ", ".join(f"{v:.2f}" for v in box) + "]"


def _tail(text: str, lines: int) -> str:
    kept = text.strip().splitlines()
    cut = len(kept) - lines
    return ("…\n" if cut > 0 else "") + "\n".join(kept[-lines:])
