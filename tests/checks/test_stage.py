"""The check stage: pipeline.toml decides which checks run, and findings never stop the run."""

from collections.abc import Callable
from typing import Any

import pytest

from irpipe.artifacts import CHECKED, IR_NORMAL, LIR
from irpipe.checks import CHECKS
from irpipe.checks.stage import CheckStage
from irpipe.core import Pipeline, RunResult
from irpipe.core.errors import PipelineConfigError, UnknownPluginError
from irpipe.frontend.measure import measure
from irpipe.frontend.normalize import normalize
from irpipe.frontend.place import place
from irpipe.frontend.resolve import Resolver
from irpipe.metrics.fixed import FixedMetrics
from irpipe.schema.ir import IRDocument

type Make = Callable[..., IRDocument]

TINY_AND_OFF: list[dict[str, Any]] = [
    {"id": "t", "type": "text", "text": "x", "at": [0, 0], "size": 20},
    {"id": "l", "type": "line", "start": [-9, 0], "end": [0, 0]},
]


def run(document: IRDocument, options: dict[str, Any]) -> RunResult:
    normal = normalize(document)
    measured, _ = measure(normal, FixedMetrics())
    assert measured is not None
    placed, _ = place(normal, measured)
    assert placed is not None
    drawing = Resolver(placed, measured).resolve()
    pipeline = Pipeline([CheckStage()], inputs=[LIR, IR_NORMAL], options={"check": options})
    return pipeline.run({LIR: drawing, IR_NORMAL: normal})


def test_only_the_listed_checks_run(document: Make) -> None:
    result = run(document(TINY_AND_OFF), {"checks": ["text_size"]})
    assert [issue.code for issue in result.issues] == ["W-SMALL-TEXT"]
    assert result.get(CHECKED) == ("text_size",)


def test_every_registered_check_runs_when_none_are_listed(document: Make) -> None:
    result = run(document(TINY_AND_OFF), {})
    assert result.get(CHECKED) == tuple(CHECKS.names())
    assert {"W-SMALL-TEXT", "W-OFFSCREEN", "W-UNSAFE"} <= {issue.code for issue in result.issues}


def test_a_check_takes_its_settings_from_its_own_table(document: Make) -> None:
    result = run(document(TINY_AND_OFF), {"checks": ["text_size"], "text_size": {"min_size": 18}})
    assert result.issues == ()


def test_an_unknown_check_is_named_with_a_suggestion(document: Make) -> None:
    with pytest.raises(UnknownPluginError, match="did you mean 'text_size'"):
        run(document(TINY_AND_OFF), {"checks": ["text_sise"]})
    with pytest.raises(PipelineConfigError, match="check 'contrast' options"):
        run(document(TINY_AND_OFF), {"checks": ["contrast"], "contrast": {"ratio": 3}})


def test_an_error_a_check_finds_does_not_stop_the_run(ir: Callable[..., dict[str, Any]]) -> None:
    data = ir([{"id": "c", "type": "circle", "center": [0, -3.6], "radius": 0.5}])
    data["frame"]["subtitle"] = {"mode": "reserve", "lines": 2, "band": [-7.6, -4.4, 7.6, -3.4]}
    result = run(IRDocument.model_validate(data), {"checks": ["subtitle"]})
    assert [issue.code for issue in result.issues] == ["E-SUBTITLE"]
    assert result.stopped_at is None
