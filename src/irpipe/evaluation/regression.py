"""Regression: every example of examples/ drawn again and compared with its reference picture.

    result = regress(Path("examples"), Path("runs/regression"), jobs=4)
    result.ready, result.ok, result.cases

A case is a folder of examples/ that holds a brief.json and a build_ir.py
(run as ``irpipe run`` runs it, with the lesson plan beside it when there
is one), or else an ir.json (compiled and drawn as ``irpipe render`` does).
A folder with neither, such as a brief for the agent alone or a LIR, is
not a case.

Every case is drawn with the project's pipeline.toml into ``<out>/<case>/``,
``jobs`` of them at once, each in a process of its own. Its frame.png is
then compared with ``examples/<case>/reference.png`` (images.py): the same,
changed (``difference.png`` is written beside it), new (there is no
reference yet) or missing (nothing was drawn). With ``update``, this run's
pictures become the references. ``regression.json`` in ``out`` holds every
case.
"""

import json
import shutil
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, Literal

from irpipe.artifacts import IR, IR_SOURCE, OUT_DIR
from irpipe.core import Pipeline, Report, Severity, load_config
from irpipe.evaluation.configs import worker_config
from irpipe.evaluation.images import compare

REFERENCE: Final = "reference.png"
SUMMARY: Final = "regression.json"
FAILED: Final = "FAILED"
"""The status of a case whose drawing raised an exception: a fault to report."""

Picture = Literal["same", "changed", "new", "missing"]


@dataclass(frozen=True)
class Case:
    name: str
    kind: Literal["run", "render"]
    """``run``: brief.json and build_ir.py through the orchestrator; ``render``: ir.json."""
    folder: Path


@dataclass(frozen=True)
class CaseResult:
    name: str
    kind: str
    status: str
    open_errors: int
    open_warnings: int
    codes: tuple[str, ...]
    """The open issues' codes."""
    picture: Picture
    difference: str
    """How the picture differs from its reference, in words; "" when there is none to say."""
    seconds: float


@dataclass(frozen=True)
class RegressionResult:
    cases: list[CaseResult]

    @property
    def ready(self) -> int:
        return sum(case.status == "READY" for case in self.cases)

    @property
    def ok(self) -> bool:
        """Every case READY, and no picture changed or missing."""
        return all(c.status == "READY" and c.picture in ("same", "new") for c in self.cases)


def cases_in(examples: Path) -> list[Case]:
    """The cases of ``examples``, by folder name."""
    found = []
    for folder in sorted(p for p in examples.iterdir() if p.is_dir()):
        if (folder / "brief.json").exists() and (folder / "build_ir.py").exists():
            found.append(Case(folder.name, "run", folder))
        elif (folder / "ir.json").exists():
            found.append(Case(folder.name, "render", folder))
    return found


def regress(
    examples: Path,
    out: Path,
    *,
    config_path: Path = Path("pipeline.toml"),
    jobs: int = 4,
    update: bool = False,
) -> RegressionResult:
    """Draw every case of ``examples`` into ``out`` and compare it with its reference."""
    out.mkdir(parents=True, exist_ok=True)
    cases = cases_in(examples)
    work = [(case, out / case.name, config_path.resolve(), out / ".cache") for case in cases]
    if jobs <= 1:
        results = [_draw(*args) for args in work]
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            results = list(pool.map(_draw, *zip(*work, strict=True)))
    if update:
        for case in cases:
            drawn = out / case.name / "frame.png"
            if drawn.exists():
                shutil.copy2(drawn, case.folder / REFERENCE)
    summary = RegressionResult(results)
    text = json.dumps([asdict(case) for case in results], indent=2, ensure_ascii=False)
    (out / SUMMARY).write_text(text + "\n", encoding="utf-8")
    return summary


def _draw(case: Case, folder: Path, config_path: Path, cache: Path) -> CaseResult:
    """One case: drawn into ``folder`` with a copy of the config, then compared."""
    started = time.perf_counter()
    shutil.rmtree(folder, ignore_errors=True)
    try:
        config = worker_config(config_path, folder / "config", cache)
        if case.kind == "run":
            from irpipe.orchestrator.run import orchestrate

            brief, script = case.folder / "brief.json", case.folder / "build_ir.py"
            report = orchestrate(brief, script, folder, config_path=config).report
        else:
            report = _render(case.folder / "ir.json", folder, config)
    except Exception as error:  # one broken case must not stop the others
        seconds = round(time.perf_counter() - started, 1)
        said = f"{type(error).__name__}: {error}"
        return CaseResult(case.name, case.kind, FAILED, 0, 0, (), "missing", said, seconds)
    found = [issue for issue in report.issues if issue.is_open]
    errors = sum(issue.severity is Severity.ERROR for issue in found)
    picture, difference = _compared(case.folder / REFERENCE, folder)
    return CaseResult(
        case.name, case.kind, str(report.status), errors, len(found) - errors,
        tuple(issue.code for issue in found), picture, difference,
        round(time.perf_counter() - started, 1),
    )  # fmt: skip


def _render(ir_path: Path, folder: Path, config_path: Path) -> Report:
    """ir.json through pipeline.toml's stages, as ``irpipe render`` does; report.json beside."""
    pipeline = Pipeline.from_config(load_config(config_path), inputs=[IR_SOURCE, OUT_DIR])
    folder.mkdir(parents=True, exist_ok=True)
    result = pipeline.run({IR_SOURCE: ir_path.read_text(encoding="utf-8"), OUT_DIR: folder})
    allows = result.get(IR).allow if IR.name in result.artifacts else ()
    report = Report.build(result.issues, allows=allows, stopped_at=result.stopped_at)
    text = report.model_dump_json(indent=2, exclude_none=True)
    (folder / "report.json").write_text(text + "\n", encoding="utf-8")
    return report


def _compared(reference: Path, folder: Path) -> tuple[Picture, str]:
    drawn = folder / "frame.png"
    if not drawn.exists():
        return "missing", "no frame.png was drawn"
    if not reference.exists():
        return "new", ""
    difference = compare(reference, drawn)
    if difference.same:
        return "same", difference.describe()
    difference.save(folder / "difference.png")
    return "changed", difference.describe()
