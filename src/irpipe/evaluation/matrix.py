"""The eval matrix: which topics are planned and drawn, how, with which models (an eval file).

    matrix = read_matrix(Path("eval/lessons.toml"))
    cells = matrix.cells()        # topic x aspect x model pair x repeat

    [eval]
    topics = ["The Pythagorean theorem", "The area of a circle"]
    aspects = ["16:9", "9:16"]    # the user's wish for every lesson of the cell
    frames = 2                    # frames per lesson (a wish too); left out, the planner chooses
    repeats = 1                   # the models answer differently each time: run a cell this often
    draw = true                   # false: plan only (fast and cheap: compares planners)
    backend = "manim"             # what draws the frames
    jobs = 8                      # cells at once, each in a process of its own

    [[eval.models]]               # one table per pairing to compare
    planner = "claude-sonnet-5-5"
    agent = "claude-haiku-5-5"

A misspelled key fails at once, with the closest name.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from irpipe.core.errors import PipelineConfigError
from irpipe.schema.render_profile import check_aspect


class ModelPair(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    planner: str = "claude-sonnet-5-5"
    agent: str = "claude-haiku-5-5"


class EvalMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    topics: tuple[str, ...] = Field(min_length=1)
    aspects: tuple[str, ...] = ("16:9",)
    frames: int | None = Field(default=2, ge=1, le=20)
    repeats: int = Field(default=1, ge=1, le=20)
    draw: bool = True
    backend: Literal["manim", "svg"] = "manim"
    jobs: int = Field(default=8, ge=1, le=64)
    lang: str | None = None
    """The language of the pictures' texts, as a wish; the planner's choice when left out."""
    models: tuple[ModelPair, ...] = (ModelPair(),)

    @field_validator("aspects")
    @classmethod
    def _aspects(cls, aspects: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(check_aspect(aspect) for aspect in aspects)

    def cells(self) -> list["Cell"]:
        """Every cell, topic by topic: each aspect, model pair and repeat."""
        found = []
        for t, topic in enumerate(self.topics, start=1):
            for aspect in self.aspects:
                for m, pair in enumerate(self.models, start=1):
                    for r in range(1, self.repeats + 1):
                        name = f"t{t:02d}-{aspect.replace(':', 'x')}-m{m}-r{r}"
                        cell = Cell(name, topic, aspect, pair.planner, pair.agent, r,
                                    self.frames, self.draw, self.backend, self.lang)  # fmt: skip
                        found.append(cell)
        return found


@dataclass(frozen=True)
class Cell:
    id: str
    """``t<topic>-<aspect>-m<model pair>-r<repeat>``: its folder's name."""
    topic: str
    aspect: str
    planner: str
    agent: str
    repeat: int
    frames: int | None
    draw: bool
    backend: str
    lang: str | None


def read_matrix(path: Path) -> EvalMatrix:
    """The ``[eval]`` table of an eval file; every failure is a ``PipelineConfigError``."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PipelineConfigError(f"eval file not found: {path}") from None
    except tomllib.TOMLDecodeError as exc:
        raise PipelineConfigError(f"{path}: not valid TOML: {exc}") from exc
    try:
        return EvalMatrix.model_validate(data.get("eval", {}))
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise PipelineConfigError(f"{path} [eval]: {problems}") from exc
