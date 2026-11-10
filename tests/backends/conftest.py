"""LIR builders for the backend tests, as fixtures."""

import copy
from collections.abc import Callable
from typing import Any

import pytest

from irpipe.schema.lir import LIRDocument

CANVAS = {"units": [16, 9], "pixels": [1920, 1080], "background": "#0E1117"}
LINE: dict[str, Any] = {
    "type": "path",
    "subpaths": [{"start": [0, 0], "segments": [{"line": [4, 0]}]}],
    "stroke": {"color": "#FFFFFF", "width": 4},
}

type MakeLIR = Callable[..., LIRDocument]
type MakeGroup = Callable[..., dict[str, Any]]


@pytest.fixture
def line() -> dict[str, Any]:
    """A white horizontal line from (0, 0) to (4, 0), 4 reference px wide."""
    return copy.deepcopy(LINE)


@pytest.fixture
def group() -> MakeGroup:
    """``group(id, *children, **fields)``: one LIR group as a dict."""
    return lambda gid, *children, **fields: {
        "type": "group",
        "id": gid,
        "children": list(children),
        **fields,
    }


@pytest.fixture
def make_lir() -> MakeLIR:
    """``make_lir(*groups, canvas=...)``: a validated LIRDocument on a 16:9 1080p frame."""

    def build(*items: dict[str, Any], canvas: dict[str, Any] | None = None) -> LIRDocument:
        return LIRDocument.model_validate(
            {"version": "lir/1.0", "canvas": canvas or CANVAS, "items": list(items)}
        )

    return build
