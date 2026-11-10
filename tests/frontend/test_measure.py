"""measure: every text and formula sized before anything is drawn; TeX mistakes as E-TEX."""

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from irpipe.artifacts import IR_NORMAL, MEASURED
from irpipe.core import Pipeline, RunResult, UnknownPluginError
from irpipe.frontend.measure import Measure, measure
from irpipe.frontend.normalize import normalize
from irpipe.metrics import MathBox, MissingToolError, TexError, TextBox
from irpipe.metrics.fixed import FixedMetrics
from irpipe.schema.ir import IRDocument

type Make = Callable[..., IRDocument]

TEXT = {"id": "t", "type": "text", "text": "ab", "at": [0, 0], "size": "label"}
MATH = {"id": "f", "type": "math", "tex": r"\frac{a}{b}", "at": [0, 0]}


class Picky(FixedMetrics):
    """Fixed sizes, but refuses one formula and misses one font, like a real machine might."""

    name = "picky"

    def math(self, tex: str, *, math_font: str, size: float) -> MathBox:
        if "fraq" in tex:
            raise TexError(r"Undefined control sequence, after: \fraq")
        if "tool" in tex:
            raise MissingToolError("latex is not installed; formulas cannot be typeset")
        return super().math(tex, math_font=math_font, size=size)

    def missing_fonts(self, families: Any) -> list[str]:
        return [f for f in families if f == "Missing Sans"]


def run(document: IRDocument, **options: Any) -> RunResult:
    pipeline = Pipeline([Measure()], inputs=[IR_NORMAL], options={"measure": options})
    return pipeline.run({IR_NORMAL: normalize(document)})


def test_every_text_and_formula_gets_a_box(document: Make) -> None:
    measured, problems = measure(normalize(document([TEXT, MATH])), FixedMetrics())
    assert problems == []
    assert measured is not None
    assert measured["t"] == TextBox(width=2 * 38 * 0.55, ascent=38 * 0.75, descent=38 * 0.25)
    assert isinstance(measured["f"], MathBox)


def test_a_tex_mistake_is_e_tex_on_the_formula_and_stops_the_run(document: Make) -> None:
    broken = {**MATH, "tex": r"\fraq{1}{2}"}
    measured, problems = measure(normalize(document([TEXT, broken])), Picky())
    assert measured is None
    (issue,) = problems
    assert (issue.code, issue.path, issue.objects) == ("E-TEX", "objects[1].tex", ("f",))
    assert issue.message == r"Undefined control sequence, after: \fraq"


def test_a_missing_tool_is_the_environments_problem(document: Make) -> None:
    measured, problems = measure(normalize(document([{**MATH, "tex": "tool"}])), Picky())
    assert measured is None
    assert [(i.code, i.origin) for i in problems] == [("E-ENVIRONMENT", "environment")]


def test_a_missing_font_is_reported_but_texts_are_still_measured(
    ir: Callable[..., dict[str, Any]],
) -> None:
    data = ir([TEXT])
    data["typography"]["text_font"] = "Missing Sans"
    measured, problems = measure(normalize(IRDocument.model_validate(data)), Picky())
    assert measured is not None and "t" in measured
    (issue,) = problems
    assert (
        issue.message == "font 'Missing Sans' is not installed; texts were measured in a substitute"
    )


def test_the_stage_hands_on_the_measurements(document: Make, tmp_path: Path) -> None:
    result = run(document([TEXT]), metrics="fixed", cache_dir=str(tmp_path))
    measured = result.get(MEASURED)
    assert set(measured) == {"t"}


def test_an_unknown_measurer_is_named(document: Make) -> None:
    with pytest.raises(UnknownPluginError, match="unknown text metrics provider 'pang'"):
        run(document([TEXT]), metrics="pang")


@pytest.mark.skipif(shutil.which("latex") is None, reason="needs latex")
def test_real_latex_errors_reach_the_agent(document: Make, tmp_path: Path) -> None:
    pytest.importorskip("pangocffi")
    result = run(document([{**MATH, "tex": r"x = \fraq{1}{2}"}]), cache_dir=str(tmp_path))
    (issue,) = result.issues
    assert (issue.code, issue.message) == ("E-TEX", r"Undefined control sequence, after: x = \fraq")
    assert result.stopped_at == "measure"
