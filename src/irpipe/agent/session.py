"""One agent session: from a brief to the best picture the agent made (analysis §1, §4).

    result = run_agent(Path("brief.json"), Path("runs/projection"))
    result.outcome.report.status, result.chosen, result.turns

1. The brief is read and the header locked; the tools the picture needs are
   checked. A problem here stops the session before the model is asked
   (the orchestrator writes its report).
2. The model writes build_ir.py and uses the tools (tools.py), one call per
   message, within ``max_calls`` messages.
3. Each ``submit`` is a turn: the orchestrator runs the script in the
   sandbox and compiles and draws the picture into ``agent/turns/<n>/``;
   its report goes back to the model.
4. The session ends when a turn is READY, when an open issue is not the
   agent's to fix (it goes to a person or the planner), after
   ``max_turns`` turns, when a turn does no better than the best before it
   (no progress), when the agent asks the planner to shorten the brief or
   split the frame (``ask_planner``), or when the messages run out (the last
   script is then compiled as a turn, if it was not submitted).
5. The best turn (READY first, then the fewest open errors, then warnings,
   then the later one) is copied into the run folder.

The run folder then holds what the orchestrator writes, and ``agent/``:
system_prompt.md, transcript.md (every message), session.json (settings,
turns, choice, cost) and the turns. When the agent asked the planner, the
report also holds an E-REPLAN issue (origin infeasible: it routes to the
planner), and ``agent/planner_request.json`` the request.
"""

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from irpipe.agent.llm import LLM_CLIENTS, LLMClient, LLMError, Message
from irpipe.agent.prompt import first_message, system_prompt, wrap
from irpipe.agent.protocol import parse
from irpipe.agent.sandbox import Sandbox, sandbox_for
from irpipe.agent.settings import AgentSettings
from irpipe.agent.tools import NAMES, Tools, describe
from irpipe.core import ISSUE_CODES, Issue, IssueCode, Origin, Report, Severity, load_config
from irpipe.core.plugins import load_plugins
from irpipe.orchestrator.environment import environment_issues
from irpipe.orchestrator.inputs import read_inputs
from irpipe.orchestrator.routing import Destination, route
from irpipe.orchestrator.run import OUTPUTS, Outcome, orchestrate
from irpipe.orchestrator.script import SCRIPT, run_script
from irpipe.schema.request import PlannerRequest

AGENT = "agent"
STUB = "# The agent did not run: the brief or the environment stopped the run first.\n"
NO_IR = (
    "there is no ir.json: the last run of build_ir.py did not write one; fix the script "
    "with run_python"
)


E_REPLAN = ISSUE_CODES.register(
    IssueCode(
        "E-REPLAN",
        Origin.INFEASIBLE,
        "the agent sends the frame back to the planner: shorten its brief or split it in two",
    )
)
REQUEST_FILE = "planner_request.json"


class AgentError(RuntimeError):
    """The session ended without a turn: the model could not be used, or wrote no script."""


@dataclass(frozen=True)
class Turn:
    number: int
    outcome: Outcome

    @property
    def counts(self) -> tuple[int, int]:
        """Open errors and open warnings."""
        found = [i for i in self.outcome.report.issues if i.is_open]
        errors = sum(i.severity is Severity.ERROR for i in found)
        return errors, len(found) - errors

    def rank(self) -> tuple[bool, int, int, int]:
        """Smaller is better: READY first, fewer errors, fewer warnings, the later turn."""
        errors, warnings = self.counts
        return (not self.outcome.report.ready, errors, warnings, -self.number)


@dataclass
class AgentResult:
    outcome: Outcome
    """The chosen turn's outcome, as the run folder now holds it (or the early stop's)."""
    turns: list[Turn] = field(default_factory=list)
    chosen: int | None = None
    calls: int = 0
    cost_usd: float = 0.0
    ended: str = ""
    """Why the session ended, in words."""
    request: PlannerRequest | None = None
    """What the agent asked the planner for, when it sent the frame back."""


def run_agent(
    brief_path: Path,
    folder: Path,
    *,
    lesson_path: Path | None = None,
    config_path: Path = Path("pipeline.toml"),
    client: LLMClient | None = None,
    sandbox: Sandbox | None = None,
) -> AgentResult:
    """Let the agent draw the frame ``brief_path`` describes into ``folder``."""
    config = load_config(config_path)
    settings = AgentSettings.from_config(config)
    folder.mkdir(parents=True, exist_ok=True)
    records = folder / AGENT
    shutil.rmtree(records, ignore_errors=True)
    records.mkdir()
    inputs, issues = read_inputs(brief_path, lesson_path)
    if inputs is not None:
        issues = environment_issues(inputs.header, config)
    if inputs is None or issues:
        stub = records / SCRIPT
        stub.write_text(STUB, encoding="utf-8")
        outcome = orchestrate(
            brief_path, stub, folder, lesson_path=lesson_path, config_path=config_path
        )
        return AgentResult(outcome, ended="stopped before the agent: " + outcome.route.describe())
    load_plugins(config.pipeline.plugins)
    box = sandbox or sandbox_for(settings.sandbox, settings.memory_mb)
    tools = Tools(records / "work", inputs, config, settings, box)
    example = _example(settings, config_path)
    system = system_prompt(settings, example)
    (records / "system_prompt.md").write_text(system, encoding="utf-8")
    session = _Session(
        settings, client or LLM_CLIENTS.get(settings.provider)(settings), tools, records,
        lambda n: _compile(n, brief_path, lesson_path, config_path, tools, box, settings),
    )  # fmt: skip
    session.talk(system, first_message(inputs))
    return session.finish(folder)


class _Session:
    def __init__(
        self,
        settings: AgentSettings,
        client: LLMClient,
        tools: Tools,
        records: Path,
        compile_turn: Callable[[int], Outcome],
    ) -> None:
        self.settings = settings
        self.client = client
        self.tools = tools
        self.records = records
        self.compile_turn = compile_turn
        self.turns: list[Turn] = []
        self.calls = 0
        self.cost = 0.0
        self.ended = ""
        self.request: PlannerRequest | None = None
        self.transcript = records / "transcript.md"

    def talk(self, system: str, first: str) -> None:
        messages = [Message("user", first)]
        self._log("user", first)
        while self.calls < self.settings.max_calls:
            try:
                reply = self.client.complete(system, messages)
            except LLMError as error:
                self.ended = f"the model could not answer: {error}"
                break
            self.calls += 1
            self.cost += reply.cost_usd or 0.0
            messages.append(Message("assistant", reply.text))
            self._log("assistant", reply.text)
            tool, result = self._act(reply.text)
            if self.ended:
                break
            answer = wrap(
                tool, result, calls_left=self.settings.max_calls - self.calls,
                turns_left=self.settings.max_turns - len(self.turns),
                limit=self.settings.result_chars,
            )  # fmt: skip
            messages.append(Message("user", answer))
            self._log("user", answer)
        else:
            self.ended = f"the model used all {self.settings.max_calls} messages"
        if not self.turns and self.tools.has_script():
            self._submit(final=True)

    def _act(self, text: str) -> tuple[str, str]:
        """Run the call in ``text``: the tool's name and its result (or the protocol's note)."""
        parsed = parse(text)
        if parsed.call is None:
            return "protocol", parsed.problem or ""
        tool, body = parsed.call.tool, parsed.call.body
        note = f"note: {parsed.problem}\n\n" if parsed.problem else ""
        if tool not in NAMES:
            return tool, f"there is no tool {tool!r}; the tools: {', '.join(NAMES)}"
        if tool == "submit":
            return tool, note + self._submit()
        if tool == "ask_planner":
            return tool, note + self._ask_planner(body)
        if tool == "run_python":
            return tool, note + self.tools.run_python(body)
        if tool in ("measure_text", "measure_tex"):
            return tool, note + getattr(self.tools, tool)(body)
        if not self.tools.has_ir():
            return tool, note + NO_IR
        result: str = getattr(self.tools, tool)()
        return tool, note + result

    def _submit(self, final: bool = False) -> str:
        if not self.tools.has_script():
            return "there is no build_ir.py to submit: write it with run_python first"
        if not self.tools.has_ir() and not final:
            return NO_IR
        found = self.tools.validate_issues() if self.tools.has_ir() else []
        refused = [i for i in found if i.severity is Severity.ERROR]
        if refused and not final:
            return "not accepted: build_ir.py must pass validate first.\n" + describe(refused)
        turn = Turn(len(self.turns) + 1, self.compile_turn(len(self.turns) + 1))
        best = min(self.turns, key=Turn.rank) if self.turns else None
        self.turns.append(turn)
        report, route = turn.outcome.report, turn.outcome.route
        said = f"turn {turn.number}: {report.headline}\n{describe(list(report.issues))}"
        if final:
            self.ended += "; its last script was compiled as a turn"
        elif route.to is Destination.DONE:
            self.ended = f"turn {turn.number} is READY"
        elif route.to is not Destination.AGENT:
            self.ended = f"turn {turn.number} stopped: {route.describe()}"
        elif turn.number >= self.settings.max_turns:
            self.ended = f"all {self.settings.max_turns} turns are used"
        elif best is not None and turn.rank()[:3] >= best.rank()[:3]:
            self.ended = f"turn {turn.number} did no better than turn {best.number} (no progress)"
        return said

    def _ask_planner(self, body: str) -> str:
        found = self.tools.ask_planner(body)
        if isinstance(found, str):
            return found
        self.request = found
        self.ended = f"the agent asked the planner to {found.kind} the brief"
        return "sent back to the planner"

    def finish(self, folder: Path) -> AgentResult:
        if self.request is not None:
            return self._back_to_planner(folder, self.request)
        if not self.turns:
            self._record(None)
            raise AgentError(self.ended or "the agent wrote no build_ir.py")
        best = min(self.turns, key=Turn.rank)
        for name in OUTPUTS:
            (folder / name).unlink(missing_ok=True)
        for path in best.outcome.files:
            shutil.copy2(path, folder / path.name)
        files = tuple(folder / p.name for p in best.outcome.files)
        outcome = Outcome(folder, best.outcome.report, best.outcome.route, files)
        self._record(best.number)
        return AgentResult(outcome, self.turns, best.number, self.calls, self.cost, self.ended)

    def _back_to_planner(self, folder: Path, request: PlannerRequest) -> AgentResult:
        """The best turn's files, if any, and a report that sends the frame to the planner."""
        best = min(self.turns, key=Turn.rank) if self.turns else None
        for name in OUTPUTS:
            (folder / name).unlink(missing_ok=True)
        files = []
        for path in best.outcome.files if best else ():
            if path.name != "report.json":
                files.append(Path(shutil.copy2(path, folder / path.name)))
        asked = "shorten its brief" if request.kind == "shorten" else "split it in two"
        what = f" ({', '.join(request.items)})" if request.items else ""
        issue = E_REPLAN(
            f"the agent asks the planner to {asked}: {request.reason}{what}",
            hint="the planner changes the brief; the agent then draws the frame again",
        )
        earlier = list(best.outcome.report.issues) if best else []
        stopped = best.outcome.report.stopped_at if best else AGENT
        report = Report.build([*earlier, issue], stopped_at=stopped)
        text = report.model_dump_json(indent=2, exclude_none=True)
        (folder / "report.json").write_text(text + "\n", encoding="utf-8")
        request_text = request.model_dump_json(indent=2)
        (self.records / REQUEST_FILE).write_text(request_text + "\n", encoding="utf-8")
        outcome = Outcome(folder, report, route(report), (*files, folder / "report.json"))
        chosen = best.number if best else None
        self._record(chosen)
        return AgentResult(outcome, self.turns, chosen, self.calls, self.cost, self.ended, request)

    def _record(self, chosen: int | None) -> None:
        record = {
            "settings": self.settings.model_dump(),
            "ended": self.ended,
            "calls": self.calls,
            "cost_usd": round(self.cost, 6),
            "chosen_turn": chosen,
            "turns": [
                {"turn": t.number, "status": str(t.outcome.report.status),
                 "open_errors": t.counts[0], "open_warnings": t.counts[1],
                 "next": t.outcome.route.describe()}
                for t in self.turns
            ],
        }  # fmt: skip
        if self.request is not None:
            record["planner_request"] = self.request.model_dump()
        text = json.dumps(record, indent=2, ensure_ascii=False)
        (self.records / "session.json").write_text(text + "\n", encoding="utf-8")

    def _log(self, role: str, text: str) -> None:
        with self.transcript.open("a", encoding="utf-8") as out:
            out.write(f"## {role}\n\n{text}\n\n")


def _compile(
    number: int,
    brief_path: Path,
    lesson_path: Path | None,
    config_path: Path,
    tools: Tools,
    box: Sandbox,
    settings: AgentSettings,
) -> Outcome:
    """A turn: the orchestrator runs the workspace's build_ir.py in the sandbox, compiles and
    draws it into agent/turns/<number>."""
    folder = tools.folder.parent / "turns" / str(number)

    def sandboxed(where: Path, timeout: float) -> list[Issue]:
        command, env = box.command(where, timeout)
        return run_script(where, timeout, command=command, env=env)

    return orchestrate(
        brief_path, tools.folder / SCRIPT, folder, lesson_path=lesson_path,
        config_path=config_path, script_timeout=settings.script_timeout, script_runner=sandboxed,
    )  # fmt: skip


def _example(settings: AgentSettings, config_path: Path) -> str | None:
    if not settings.example:
        return None
    path = Path(settings.example)
    path = path if path.is_absolute() else config_path.parent / path
    return path.read_text(encoding="utf-8") if path.exists() else None
