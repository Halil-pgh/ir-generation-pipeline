"""Stage "measure": the size of every text and formula, as the backend will draw it.

    requires  ir_normal
    provides  measured    object id -> TextBox (a text) or MathBox (a formula)
    options   metrics = "pango"    the measurer (irpipe/metrics)
              cache_dir = "..."    where typeset formulas are kept; "" keeps none

Formulas are typeset here, before anything is drawn, so a TeX mistake comes
back as E-TEX with the formula's path (analysis §3). Measurements are cached:
in memory, and formulas also on disk.

    E-TEX          a formula cannot be typeset; the run stops here
    E-ENVIRONMENT  the measurer, LaTeX or a font is missing
"""

from pathlib import Path
from typing import Any

from irpipe.artifacts import IR_NORMAL, MEASURED
from irpipe.backends.base import E_ENVIRONMENT
from irpipe.core import ISSUE_CODES, STAGES, Issue, IssueCode, Origin, Stage, StageContext
from irpipe.frontend.labels import source_paths
from irpipe.metrics import (
    METRICS,
    CachedMetrics,
    MissingToolError,
    TexError,
    TextBox,
    TextMetrics,
    default_folder,
)
from irpipe.schema.ir import IRDocument, Math, Text

E_TEX = ISSUE_CODES.register(IssueCode("E-TEX", Origin.IR, "a formula's TeX cannot be typeset"))

DEFAULT_METRICS = "pango"


@STAGES.register
class Measure(Stage):
    name = "measure"
    requires = (IR_NORMAL,)
    provides = (MEASURED,)

    def run(self, ctx: StageContext) -> None:
        chosen = str(ctx.options.get("metrics", DEFAULT_METRICS))
        try:
            provider = METRICS.get(chosen)()
        except MissingToolError as exc:
            ctx.report(E_ENVIRONMENT(str(exc), hint='pip install -e ".[pango]"'))
            return
        folder = ctx.options.get("cache_dir")
        metrics = CachedMetrics(
            provider, default_folder() if folder is None else (Path(folder) if folder else None)
        )
        measured, problems = measure(ctx.read(IR_NORMAL), metrics)
        ctx.report(*problems)
        if measured is not None:
            ctx.write(MEASURED, measured)


def measure(
    document: IRDocument, metrics: TextMetrics
) -> tuple[dict[str, Any] | None, list[Issue]]:
    """Every text's and formula's box, and the problems met; None when a formula failed."""
    problems: list[Issue] = []
    texts = [obj for obj in document.objects if isinstance(obj, Text)]
    font = document.typography.text_font
    if texts and metrics.missing_fonts([font]):
        problems.append(
            E_ENVIRONMENT(
                f"font '{font}' is not installed; texts were measured in a substitute",
                hint="install the font, or choose one that is installed",
            )
        )
    measured: dict[str, TextBox] = {}
    failed = False
    paths = source_paths(document)
    for obj in document.objects:
        if isinstance(obj, Text):
            measured[obj.id] = metrics.text(
                obj.text,
                font=font,
                size=_px(obj.size),
                weight=obj.weight or "regular",
                italic=bool(obj.italic),
            )
        elif isinstance(obj, Math):
            try:
                measured[obj.id] = metrics.math(
                    obj.tex, math_font=document.typography.math, size=_px(obj.size)
                )
            except TexError as exc:
                failed = True
                problems.append(
                    E_TEX(
                        str(exc),
                        path=f"{paths[obj.id]}.tex",
                        objects=[obj.id],
                        hint="check braces and command names; words inside a formula go "
                        "in \\text{...}",
                    )
                )
            except MissingToolError as exc:
                problems.append(E_ENVIRONMENT(str(exc), hint="install TeX Live and dvisvgm"))
                return None, problems
    return (None if failed else measured), problems


def _px(size: float | str | None) -> float:
    """A normalized size is reference pixels; normalize made sure it is a number."""
    if not isinstance(size, int | float):
        raise TypeError(f"measure needs a normalized IR; got size {size!r}")
    return float(size)
