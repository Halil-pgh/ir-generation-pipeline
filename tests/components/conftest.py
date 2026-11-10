"""Opening components: helpers that run validate (and the front-end) on a small IR.

document = opened([axes])           # the IR after validate: core objects only
issues = refused([axes])            # what validate reported instead
drawing = drawn([axes])             # the LIR, measured with the "fixed" measurer
"""

import json
from collections.abc import Callable
from typing import Any

import pytest

from irpipe.artifacts import IR, IR_SOURCE
from irpipe.core import Issue, Pipeline
from irpipe.core.plugins import load_plugins
from irpipe.frontend.measure import measure
from irpipe.frontend.normalize import normalize
from irpipe.frontend.place import place
from irpipe.frontend.resolve import Resolver
from irpipe.frontend.validate import Validate
from irpipe.metrics.fixed import FixedMetrics
from irpipe.schema.ir import IRDocument
from irpipe.schema.lir import LIRDocument

load_plugins(["irpipe.components"])

type Build = Callable[..., dict[str, Any]]


def _validate(ir: dict[str, Any]) -> tuple[IRDocument | None, tuple[Issue, ...]]:
    result = Pipeline([Validate()], inputs=[IR_SOURCE]).run({IR_SOURCE: json.dumps(ir)})
    document = result.get(IR) if IR.name in result.artifacts else None
    return document, result.issues


@pytest.fixture
def opened(ir: Build) -> Callable[..., IRDocument]:
    """``opened(objects, **body)``: the validated IR; fails on any error."""

    def run(objects: list[dict[str, Any]], **body: Any) -> IRDocument:
        document, issues = _validate(ir(objects, **body))
        errors = [i for i in issues if i.code.startswith("E-")]
        assert document is not None and not errors, issues
        return document

    return run


@pytest.fixture
def refused(ir: Build) -> Callable[..., tuple[Issue, ...]]:
    """``refused(objects, **body)``: the issues validate reported."""
    return lambda objects, **body: _validate(ir(objects, **body))[1]


@pytest.fixture
def drawn(opened: Callable[..., IRDocument]) -> Callable[..., LIRDocument]:
    """``drawn(objects, **body)``: the LIR the front-end makes of it."""

    def run(objects: list[dict[str, Any]], **body: Any) -> LIRDocument:
        normal = normalize(opened(objects, **body))
        measured, problems = measure(normal, FixedMetrics())
        assert measured is not None, problems
        placed, problems = place(normal, measured)
        assert placed is not None, problems
        return Resolver(placed, measured).resolve()

    return run
