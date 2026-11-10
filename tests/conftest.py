"""Builders for small IR documents, shared by the front-end and check tests."""

import copy
import json
from collections.abc import Callable
from typing import Any

import pytest

from irpipe.schema.ir import IRDocument

HEADER: dict[str, Any] = {
    "version": "frame-ir/1.0",
    "intent": "a test picture",
    "frame": {
        "aspect": "16:9",
        "pixels": [1920, 1080],
        "units": [16, 9],
        "platform": "plain",
        "background": "#0E1117",
        "subtitle": {"mode": "none", "lines": 2},
        "safe": [-7.6, -4.1, 7.6, 4.1],
    },
    "typography": {
        "lang": "en",
        "text_font": "Inter",
        "math": "latin-modern",
        "sizes": {"title": 64, "heading": 52, "body": 42, "label": 38, "caption": 34},
    },
    "colors": {"a": "#FFD43B", "b": [88, 196, 221]},
    "styles": {
        "muted": {"opacity": 0.5},
        "dashed": {"dash": [14, 10], "stroke_width": 3},
        "boxed": {"fill": "a", "color": "b"},
    },
}

type Build = Callable[..., dict[str, Any]]


@pytest.fixture
def ir() -> Build:
    """``ir(objects, **body)``: a whole IR as a dict; a header field can be overridden too."""

    def build(objects: list[dict[str, Any]] | None = None, **fields: Any) -> dict[str, Any]:
        return {**copy.deepcopy(HEADER), "objects": objects or [], **fields}

    return build


@pytest.fixture
def ir_text(ir: Build) -> Callable[..., str]:
    return lambda *args, **kwargs: json.dumps(ir(*args, **kwargs))


@pytest.fixture
def document(ir: Build) -> Callable[..., IRDocument]:
    return lambda *args, **kwargs: IRDocument.model_validate(ir(*args, **kwargs))
