"""The ``irpipe`` command: turn one ir.json, or one brief, into a picture.

    irpipe render examples/projection/ir.json          # into runs/projection/
    irpipe render my/ir.json -o out/ --config pipeline.toml
    irpipe run examples/projection/brief.json examples/projection/build_ir.py
    irpipe agent examples/projection/brief.json        # the agent writes build_ir.py
    irpipe plan "vector projection" --frames 3         # the planner: into lessons/<topic>/
    irpipe lesson "vector projection" --aspect 9:16    # plan, then draw every frame

``render`` runs the stages ``pipeline.toml`` lists on an IR written by hand.
Next to the backend's files it writes lir.json and report.json, then
prints the report.

``run`` is the orchestrator (irpipe/orchestrator): from the planner's brief
it locks the header, runs the agent's build_ir.py, compiles and draws what
it wrote, and fills the whole run folder (runs/<brief id> by default); it
prints the report and who acts next.

``agent`` lets the IR agent (irpipe/agent) write build_ir.py for the brief,
with the model pipeline.toml's ``[agent]`` names; each submission is drawn,
and the best one fills the run folder. It prints every turn, then the
chosen turn's report.

``plan`` lets the planner (irpipe/planner) turn a topic into a lesson plan
and a brief per frame, in lessons/<topic> by default; ``lesson`` then has
the agent draw every frame, sends a frame that does not fit back to the
planner, and writes lesson.json. ``--frames``, ``--aspect``, ``--platform``
and ``--lang`` are the user's wishes: they win over the planner's choice.

The exit status is 0 when the picture is READY, 1 when it is not, 2 when
the command itself could not run.
"""

import argparse
import json
import re
import sys
import unicodedata
from collections.abc import Iterable
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
    run = commands.add_parser("run", help="draw one frame from its brief and the agent's script")
    run.add_argument("brief", type=Path, help="the planner's brief.json")
    run.add_argument("script", type=Path, help="the agent's build_ir.py, which writes ir.json")
    run.add_argument(
        "--lesson", type=Path, help="the lesson plan (default: lesson_plan.json beside the brief)"
    )
    run.add_argument("-o", "--out", type=Path, help="run folder (default: runs/<brief id>)")
    run.add_argument(
        "--config", type=Path, default=Path("pipeline.toml"), help="pipeline file to run"
    )
    agent = commands.add_parser("agent", help="let the IR agent draw one frame from its brief")
    agent.add_argument("brief", type=Path, help="the planner's brief.json")
    agent.add_argument(
        "--lesson", type=Path, help="the lesson plan (default: lesson_plan.json beside the brief)"
    )
    agent.add_argument("-o", "--out", type=Path, help="run folder (default: runs/<brief id>)")
    agent.add_argument(
        "--config", type=Path, default=Path("pipeline.toml"), help="pipeline file to run"
    )
    for name, about in (
        ("plan", "let the planner write a lesson plan and its briefs from a topic"),
        ("lesson", "plan a lesson from a topic, then let the agent draw every frame"),
    ):
        command = commands.add_parser(name, help=about)
        command.add_argument("topic", help="what the lesson is about, in words")
        command.add_argument(
            "-o", "--out", type=Path, help="lesson folder (default: lessons/<topic>)"
        )
        command.add_argument("--frames", type=int, help="exactly this many frames")
        command.add_argument("--aspect", help="the frames' aspect, such as 16:9 or 9:16")
        command.add_argument("--platform", help="where the frames are shown, such as tiktok")
        command.add_argument("--lang", help="the language of the texts, such as en or tr")
        command.add_argument(
            "--config", type=Path, default=Path("pipeline.toml"), help="pipeline file to run"
        )
    args = parser.parse_args(argv)
    try:
        if args.command in ("plan", "lesson"):
            return plan_command(args)
        if args.command == "run":
            return run_brief(args.brief, args.script, args.out, args.lesson, args.config)
        if args.command == "agent":
            return run_agent_command(args.brief, args.out, args.lesson, args.config)
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


def run_brief(
    brief: Path, script: Path, out: Path | None, lesson: Path | None, config: Path
) -> int:
    from irpipe.orchestrator.run import orchestrate

    folder = out or Path("runs") / _brief_id(brief)
    outcome = orchestrate(brief, script, folder, lesson_path=lesson, config_path=config)
    _print(outcome.report, outcome.files)
    print(f"next: {outcome.route.describe()}")
    return 0 if outcome.report.ready else 1


def run_agent_command(brief: Path, out: Path | None, lesson: Path | None, config: Path) -> int:
    from irpipe.agent import AgentError, LLMError, run_agent

    folder = out or Path("runs") / _brief_id(brief)
    try:
        result = run_agent(brief, folder, lesson_path=lesson, config_path=config)
    except (AgentError, LLMError) as exc:
        print(f"irpipe: the agent made no picture: {exc}", file=sys.stderr)
        return 2
    for turn in result.turns:
        errors, warnings = turn.counts
        status = str(turn.outcome.report.status).replace("_", " ")
        counts = f"{_count(errors, 'error')}, {_count(warnings, 'warning')}"
        print(f"turn {turn.number}: {status} ({counts})")
    if result.turns:
        cost = f", ${result.cost_usd:.4f}" if result.cost_usd else ""
        print(f"chose turn {result.chosen} ({result.calls} messages{cost}); {result.ended}")
    _print(result.outcome.report, result.outcome.files)
    print(f"next: {result.outcome.route.describe()}")
    return 0 if result.outcome.report.ready else 1


def plan_command(args: argparse.Namespace) -> int:
    from pydantic import ValidationError

    from irpipe.agent import LLMError
    from irpipe.planner import PlannerError, Wishes, plan, run_lesson

    try:
        wishes = Wishes(
            frames=args.frames, aspect=args.aspect, platform=args.platform, lang=args.lang
        )
    except ValidationError as exc:
        problems = "; ".join(error["msg"].removeprefix("Value error, ") for error in exc.errors())
        print(f"irpipe: {problems}", file=sys.stderr)
        return 2
    folder = args.out or Path("lessons") / slug(args.topic)
    try:
        if args.command == "plan":
            planned = plan(args.topic, folder, wishes=wishes, config_path=args.config)
        else:
            lesson = run_lesson(args.topic, folder, wishes=wishes, config_path=args.config)
    except (PlannerError, LLMError) as exc:
        print(f"irpipe: the planner made no lesson: {exc}", file=sys.stderr)
        return 2
    if args.command == "plan":
        cost = f", ${planned.cost_usd:.4f}" if planned.cost_usd else ""
        print(f"lesson {planned.lesson.id!r}: {_count(len(planned.briefs), 'frame')}"
              f" ({_count(planned.answers, 'answer')}{cost})")  # fmt: skip
        for outline in planned.lesson.frames:
            print(f"  {outline.id} ({outline.purpose}): {outline.summary}")
        for path in [folder / "lesson_plan.json", *planned.briefs.values()]:
            print(f"  -> {path}")
        return 0
    for back in lesson.returns:
        print(f"back to the planner: {back.frame} ({back.kind}) -> {', '.join(back.became)}")
    for frame in lesson.frames:
        status = frame.status.replace("_", " ")
        where = f" -> {folder / frame.folder}" if frame.folder else ""
        print(f"{frame.frame}: {status}; {frame.next}{where}")
    cost = f" (${lesson.cost_usd:.4f})" if lesson.cost_usd else ""
    print(f"{lesson.ended}{cost} -> {folder / 'lesson.json'}")
    return 0 if lesson.ready else 1


def slug(topic: str) -> str:
    """A folder name for a topic: its letters and digits, without accents, joined by _."""
    dotless = topic.replace("\u0131", "i")  # the Turkish dotless i has no accent to take off
    plain = unicodedata.normalize("NFKD", dotless).encode("ascii", "ignore")
    words = re.findall(r"[a-z0-9]+", plain.decode().lower())
    return "_".join(words)[:48].strip("_") or "lesson"


def _count(number: int, word: str) -> str:
    return f"{number} {word}{'' if number == 1 else 's'}"


def _brief_id(brief: Path) -> str:
    """The brief's id, for the run folder's name; the file's folder when it cannot be read."""
    try:
        frame_id = json.loads(brief.read_text(encoding="utf-8")).get("id")
    except (OSError, ValueError, AttributeError):
        frame_id = None
    return frame_id if isinstance(frame_id, str) and frame_id else brief.parent.name or "run"


def _print(report: Report, written: Iterable[Path]) -> None:
    print(report.headline)
    for issue in report.issues:
        where = f" {issue.path}" if issue.path else ""
        mark = " (allowed)" if not issue.is_open else ""
        print(f"  {issue.code}{where}: {issue.message}{mark}")
        if issue.hint:
            print(f"      hint: {issue.hint}")
    for path in written:
        print(f"  -> {path}")


def _report(result: RunResult) -> Report:
    """The run's report, with the IR's allow entries applied when there is an IR."""
    allows = result.get(IR).allow if IR.name in result.artifacts else ()
    return Report.build(result.issues, allows=allows, stopped_at=result.stopped_at)


if __name__ == "__main__":
    raise SystemExit(main())
