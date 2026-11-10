"""Stage "check": runs the checks pipeline.toml lists over the drawn picture.

    requires  lir         what resolve drew
              ir_normal   the IR, for what the agent meant (references, groups, header)
    provides  checked     the names of the checks that ran
    options   checks = ["offscreen", ...]   which checks run, in order; all when left out
              [options.check.<name>]        a check's settings

Findings are issues: warnings an ``allow`` entry can accept, and errors
(``E-SUBTITLE``). Either way the stage writes its output, so the run goes
on and the picture is drawn; the report says whether it is READY.
"""

from irpipe.artifacts import CHECKED, IR_NORMAL, LIR
from irpipe.checks.base import CHECKS
from irpipe.checks.picture import Picture
from irpipe.core import STAGES, Stage, StageContext


@STAGES.register
class CheckStage(Stage):
    name = "check"
    requires = (LIR, IR_NORMAL)
    provides = (CHECKED,)

    def run(self, ctx: StageContext) -> None:
        names = [str(name) for name in ctx.options.get("checks", CHECKS.names())]
        checks = [CHECKS.get(name)(ctx.options.get(name, {})) for name in names]
        picture = Picture(ctx.read(LIR), ctx.read(IR_NORMAL))
        for check in checks:
            ctx.report(*check.check(picture))
        ctx.write(CHECKED, tuple(names))
