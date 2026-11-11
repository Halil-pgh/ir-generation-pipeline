"""Reads ``pipeline.toml``: which stages run, in which order, with which options.

The file is the one place where the pipeline's shape is decided, so adding or
removing a stage never needs a code change. Unknown keys are rejected, so a
typo such as ``stagse`` fails loudly instead of being silently ignored.

    [pipeline]
    stages  = ["validate", "resolve"]   # run in this order
    plugins = ["irpipe.frontend"]       # packages whose modules register stages

    [options.resolve]                   # handed to that stage as ctx.options
    label_gap = 0.15

    [agent]                             # the IR agent's settings (irpipe/agent, step 21)
    model = "claude-haiku-5-5"
"""

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from irpipe.core.errors import PipelineConfigError


class PipelineSection(BaseModel):
    """The ``[pipeline]`` table."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    stages: list[str] = Field(default_factory=list)
    """Stage names, in run order."""

    plugins: list[str] = Field(default_factory=list)
    """Packages to import before the stages are looked up, so their plugins register."""


class PipelineConfig(BaseModel):
    """The whole of ``pipeline.toml``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pipeline: PipelineSection = Field(default_factory=PipelineSection)
    options: dict[str, dict[str, Any]] = Field(default_factory=dict)
    """Per-stage settings: ``[options.<stage>]`` becomes that stage's ``ctx.options``."""

    agent: dict[str, Any] = Field(default_factory=dict)
    """The IR agent's settings, ``[agent]``; the agent checks them itself (irpipe/agent)."""


def load_config(path: Path) -> PipelineConfig:
    """Read and validate a pipeline.toml file; every failure is a ``PipelineConfigError``."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PipelineConfigError(f"config file not found: {path}") from None
    except tomllib.TOMLDecodeError as exc:
        raise PipelineConfigError(f"{path}: not valid TOML: {exc}") from exc
    try:
        return PipelineConfig.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise PipelineConfigError(f"{path}: {problems}") from exc
