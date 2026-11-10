"""Stage "render": hands the LIR to the chosen backend and collects its files.

    requires  lir, out_dir
    provides  rendered     the files written, as Paths
    options   backend = "svg"; settings for it in [options.render.<backend>]

When the LIR uses a feature the backend cannot draw, the stage reports
E-CAPABILITY and draws nothing; lowering such features comes with step 14.
"""

from irpipe.artifacts import LIR, OUT_DIR, RENDERED
from irpipe.backends.base import BACKENDS, unsupported
from irpipe.core import STAGES, Stage, StageContext

DEFAULT_BACKEND = "svg"


@STAGES.register
class Render(Stage):
    name = "render"
    requires = (LIR, OUT_DIR)
    provides = (RENDERED,)

    def run(self, ctx: StageContext) -> None:
        chosen = str(ctx.options.get("backend", DEFAULT_BACKEND))
        backend = BACKENDS.get(chosen)(ctx.options.get(chosen, {}))
        lir = ctx.read(LIR)
        problems = unsupported(lir, backend)
        if problems:
            ctx.report(*problems)
            return
        out_dir = ctx.read(OUT_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        rendered = backend.render(lir, out_dir)
        ctx.report(*rendered.issues)
        ctx.write(RENDERED, rendered.files)
