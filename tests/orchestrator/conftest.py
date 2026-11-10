"""A run folder to play in: the example's brief, lesson and script, and a pipeline.toml.

``example(**brief_changes)`` copies the example's brief (changed), lesson plan
and build_ir.py into a folder; ``svg_config`` is the repository's
pipeline.toml, drawing with the SVG backend.
"""

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parent.parent.parent
EXAMPLE = ROOT / "examples" / "projection"


@pytest.fixture
def example(tmp_path: Path) -> Callable[..., Path]:
    """``example(**brief_changes)``: a folder with the example's brief (changed), lesson and
    script; returns the folder."""

    def make(**changes: Any) -> Path:
        folder = tmp_path / "in"
        folder.mkdir(exist_ok=True)
        brief = {**json.loads((EXAMPLE / "brief.json").read_text(encoding="utf-8")), **changes}
        (folder / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
        shutil.copy(EXAMPLE / "lesson_plan.json", folder / "lesson_plan.json")
        shutil.copy(EXAMPLE / "build_ir.py", folder / "build_ir.py")
        return folder

    return make


@pytest.fixture
def svg_config(tmp_path: Path) -> Path:
    """The repository's pipeline.toml, drawing with the SVG backend (fast, no Manim)."""
    text = (ROOT / "pipeline.toml").read_text(encoding="utf-8")
    assert 'backend = "manim"' in text
    path = tmp_path / "pipeline.toml"
    path.write_text(text.replace('backend = "manim"', 'backend = "svg"'), encoding="utf-8")
    return path
