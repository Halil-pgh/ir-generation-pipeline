"""Who acts next: the open issues of a run, sent where their origin says (analysis §1).

    route(report).to        # done, agent, planner or human
    route(report).issues    # the open issues that go there

    origin          goes to
    ir              the agent, in IR terms
    capability      the agent (what could be lowered already was)
    infeasible      the planner: shorten, or split into two frames
    internal        a person: a fault in the compiler
    environment     a person: a tool is missing

When issues of several origins are open at once, a person comes first,
then the planner, then the agent: the agent cannot fix what a missing tool
or a broken compiler causes, and its fixes are lost if the planner changes
the frame.
"""

from dataclasses import dataclass
from enum import StrEnum

from irpipe.core import Issue, Origin, Report


class Destination(StrEnum):
    DONE = "done"
    AGENT = "agent"
    PLANNER = "planner"
    HUMAN = "human"


SENT_TO = {
    Origin.IR: Destination.AGENT,
    Origin.CAPABILITY: Destination.AGENT,
    Origin.INFEASIBLE: Destination.PLANNER,
    Origin.INTERNAL: Destination.HUMAN,
    Origin.ENVIRONMENT: Destination.HUMAN,
}
FIRST = (Destination.HUMAN, Destination.PLANNER, Destination.AGENT)


@dataclass(frozen=True)
class Route:
    to: Destination
    issues: tuple[Issue, ...] = ()

    def describe(self) -> str:
        if self.to is Destination.DONE:
            return "done: the picture is ready"
        count = f"{len(self.issues)} issue{'' if len(self.issues) == 1 else 's'}"
        work = {
            Destination.AGENT: "to fix in the IR",
            Destination.PLANNER: "to fix in the brief",
            Destination.HUMAN: "that the agent cannot fix",
        }[self.to]
        return f"{self.to}: {count} {work}"


def route(report: Report) -> Route:
    """Where the run goes next: done when ready, else the first destination with open issues."""
    open_issues = [issue for issue in report.issues if issue.is_open]
    if not open_issues:
        return Route(Destination.DONE)
    for destination in FIRST:
        mine = tuple(issue for issue in open_issues if SENT_TO[issue.origin] is destination)
        if mine:
            return Route(destination, mine)
    raise AssertionError("every origin has a destination")
