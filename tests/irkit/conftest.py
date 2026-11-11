"""A picture to build in: the shared test header, measured with the "fixed" measurer.

``pic`` is a Picture on the test header (tests/conftest.py), so no fonts or
LaTeX are needed; ``header`` is that header as a dict.
"""

from collections.abc import Callable
from typing import Any

import pytest

from irpipe.irkit import Picture
from irpipe.schema.ir import HEADER_FIELDS


@pytest.fixture
def header(ir: Callable[..., dict[str, Any]]) -> dict[str, Any]:
    return {name: value for name, value in ir([]).items() if name in HEADER_FIELDS}


@pytest.fixture
def pic(header: dict[str, Any]) -> Picture:
    return Picture(header, metrics="fixed")
