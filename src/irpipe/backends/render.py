"""Stage "render": lowers the LIR for the chosen backend, which draws it, and collects its files.

    requires  lir, out_dir
    provides  rendered     the files written, as Paths
    options   backend = "svg"; settings for it in [options.render.<backend>]

The backend is chosen here and only here, so lowering happens here too:
every feature the backend does not list is rewritten with simpler ones
first (frontend/lower.py). What cannot be lowered is reported in IR terms
(E-CAPABILITY, E-ENVIRONMENT) and nothing is drawn. lir.json stays the
backend-independent LIR.
"""

from irpipe.artifacts import LIR, OUT_DIR, RENDERED
from irpipe.backends.base import BACKENDS, unsupported
from irpipe.core import STAGES, Stage, StageContext
from irpipe.frontend.lower import lower

DEFAULT_BACKEND = "svg"


@STAGES.register
class Render(Stage):
    name = "render"
    requires = (LIR, OUT_DIR)
    provides = (RENDERED,)

    def run(self, ctx: StageContext) -> None:
        chosen = str(ctx.options.get("backend", DEFAULT_BACKEND))
        backend = BACKENDS.get(chosen)(ctx.options.get(chosen, {}))
        lir, problems = lower(ctx.read(LIR), backend.capabilities)
        problems += unsupported(lir, backend)  # lowering leaves nothing; this only guards it
        if problems:
            ctx.report(*problems)
            return
        out_dir = ctx.read(OUT_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        rendered = backend.render(lir, out_dir)
        ctx.report(*rendered.issues)
        ctx.write(RENDERED, rendered.files)
