"""Stage "check_header": the IR must carry the header the orchestrator locked.

    requires  ir, locked_header
    provides  nothing; a changed header is an E-HEADER error

The orchestrator writes the header from the brief (step 19) and the agent
may only write the body. The two headers are compared by hash (analysis §1);
when they differ, the issue names the fields that changed, so the agent
knows what to put back.

The stage is not in the default pipeline.toml: a hand-run has no locked
header. The orchestrator adds it, with the header it wrote as an input.
"""

from typing import Any

from irpipe.artifacts import IR, LOCKED_HEADER
from irpipe.core import ISSUE_CODES, STAGES, IssueCode, Origin, Stage, StageContext
from irpipe.schema.ir import header_hash

E_HEADER = ISSUE_CODES.register(
    IssueCode("E-HEADER", Origin.IR, "the header differs from the one the orchestrator locked")
)

SHOWN = 5
"""How many changed fields the message lists before it says "and N more"."""


@STAGES.register
class CheckHeader(Stage):
    name = "check_header"
    requires = (IR, LOCKED_HEADER)

    def run(self, ctx: StageContext) -> None:
        written, locked = ctx.read(IR).header, ctx.read(LOCKED_HEADER)
        if header_hash(written) == header_hash(locked):
            return
        changed = differences(locked.model_dump(mode="json"), written.model_dump(mode="json"))
        listed = ", ".join(changed[:SHOWN])
        more = f" and {len(changed) - SHOWN} more" if len(changed) > SHOWN else ""
        ctx.report(
            E_HEADER(
                f"the header was changed at {listed}{more}",
                path=changed[0] if changed else None,
                hint="the header is locked: copy it back exactly as given, change only the body",
            )
        )


def differences(locked: Any, written: Any, path: str = "") -> list[str]:
    """JSON paths where ``written`` differs from ``locked``."""
    if isinstance(locked, dict) and isinstance(written, dict):
        found: list[str] = []
        for key in sorted(set(locked) | set(written)):
            where = f"{path}.{key}" if path else str(key)
            found += differences(locked.get(key), written.get(key), where)
        return found
    if isinstance(locked, list) and isinstance(written, list) and len(locked) == len(written):
        return [
            p
            for k, (a, b) in enumerate(zip(locked, written, strict=True))
            for p in differences(a, b, f"{path}[{k}]")
        ]
    return [] if locked == written else [path]
