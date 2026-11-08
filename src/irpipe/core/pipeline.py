"""Builds a chain of stages, checks that the chain is complete, and runs it.

This is where plug-and-play is made safe. Creating a ``Pipeline`` walks the
stages in order and refuses to start when

- a stage requires an artifact that neither the inputs nor an earlier stage
  provides (typically: the stage that made it was removed or moved later), or
- two producers would write the same artifact.

Every error names the stage and the artifact. While running, each stage gets a
``StageContext`` that enforces its declared reads and writes.

    pipeline = Pipeline.build(["validate", "resolve"], inputs=[IR])
    result = pipeline.run({IR: ir_document})
    lir = result.get(LIR)
"""

import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from irpipe.core.artifact import ArtifactKey
from irpipe.core.config import PipelineConfig
from irpipe.core.context import StageContext
from irpipe.core.errors import (
    PipelineConfigError,
    PipelineError,
    StageContractError,
    StageFailedError,
)
from irpipe.core.plugins import load_plugins
from irpipe.core.registry import Registry
from irpipe.core.stage import STAGES, Stage

type StageOptions = Mapping[str, Mapping[str, Any]]


@dataclass(frozen=True)
class StageRun:
    """How one stage went in one run (meta.json uses this later)."""

    name: str
    seconds: float


@dataclass(frozen=True)
class RunResult:
    """Everything a run produced: all artifacts, and the stages in the order they ran."""

    artifacts: Mapping[str, object]
    stages: tuple[StageRun, ...]

    def get[T](self, key: ArtifactKey[T]) -> T:
        """The artifact ``key``, type-checked."""
        if key.name not in self.artifacts:
            raise KeyError(f"the run produced no artifact '{key}'")
        value = self.artifacts[key.name]
        if not isinstance(value, key.value_type):
            raise TypeError(f"artifact '{key}' is a {type(value).__name__}")
        return value


class Pipeline:
    """An ordered, checked chain of stages."""

    def __init__(
        self,
        stages: Sequence[Stage],
        inputs: Iterable[ArtifactKey[Any]],
        options: StageOptions | None = None,
    ) -> None:
        self._stages = tuple(stages)
        self._inputs = tuple(inputs)
        self._options = {name: dict(values) for name, values in (options or {}).items()}
        _check_chain(self._stages, self._inputs)

    @classmethod
    def build(
        cls,
        stage_names: Sequence[str],
        *,
        inputs: Iterable[ArtifactKey[Any]],
        options: StageOptions | None = None,
        registry: Registry[type[Stage]] = STAGES,
    ) -> "Pipeline":
        """Look the stages up by name and create the pipeline.

        Options may name stages that are registered but not in this pipeline
        (a stage switched off keeps its settings); a name that is not
        registered at all is treated as a typo and rejected.
        """
        for name in options or {}:
            registry.get(name)  # raises UnknownPluginError, with a "did you mean"
        stages = [registry.get(name)() for name in stage_names]
        return cls(stages, inputs, options)

    @classmethod
    def from_config(
        cls,
        config: PipelineConfig,
        *,
        inputs: Iterable[ArtifactKey[Any]],
        registry: Registry[type[Stage]] = STAGES,
    ) -> "Pipeline":
        """Import the configured plugin packages, then build the configured stages."""
        load_plugins(config.pipeline.plugins)
        return cls.build(
            config.pipeline.stages, inputs=inputs, options=config.options, registry=registry
        )

    @property
    def stage_names(self) -> tuple[str, ...]:
        return tuple(stage.name for stage in self._stages)

    @property
    def inputs(self) -> tuple[ArtifactKey[Any], ...]:
        return self._inputs

    def run(self, inputs: Mapping[ArtifactKey[Any], object]) -> RunResult:
        """Run every stage in order on the given input artifacts."""
        artifacts = self._take_inputs(inputs)
        runs: list[StageRun] = []
        for stage in self._stages:
            ctx = StageContext(
                stage.name,
                artifacts,
                readable=stage.requires,
                writable=stage.provides,
                options=self._options.get(stage.name, {}),
            )
            started = time.perf_counter()
            try:
                stage.run(ctx)
            except PipelineError:
                raise
            except Exception as exc:
                raise StageFailedError(stage.name, exc) from exc
            missing = ctx.unwritten()
            if missing:
                raise StageContractError(
                    f"stage '{stage.name}' finished without writing {', '.join(missing)}"
                )
            runs.append(StageRun(stage.name, time.perf_counter() - started))
        return RunResult(MappingProxyType(artifacts), tuple(runs))

    def _take_inputs(self, inputs: Mapping[ArtifactKey[Any], object]) -> dict[str, object]:
        expected = {key.name for key in self._inputs}
        given = {key.name for key in inputs}
        if given != expected:
            raise PipelineConfigError(
                f"run() needs exactly the inputs {sorted(expected)}, got {sorted(given)}"
            )
        artifacts: dict[str, object] = {}
        for key, value in inputs.items():
            if not isinstance(value, key.value_type):
                raise PipelineConfigError(
                    f"input '{key}' must be {key.value_type.__name__}, got {type(value).__name__}"
                )
            artifacts[key.name] = value
        return artifacts


def _check_chain(stages: Sequence[Stage], inputs: Sequence[ArtifactKey[Any]]) -> None:
    """Raise ``PipelineConfigError`` unless every artifact has exactly one earlier producer."""
    producer: dict[str, str] = {key.name: "the inputs" for key in inputs}
    later_producer = {key.name: stage.name for stage in stages for key in stage.provides}
    seen: set[str] = set()
    for stage in stages:
        if stage.name in seen:
            raise PipelineConfigError(f"stage '{stage.name}' appears twice in the pipeline")
        seen.add(stage.name)
        for key in stage.requires:
            if key.name in producer:
                continue
            message = (
                f"stage '{stage.name}' requires artifact '{key}', "
                "but neither the inputs nor an earlier stage provides it"
            )
            if key.name in later_producer:
                message += f" ('{later_producer[key.name]}' provides it but runs later)"
            message += f"; available at that point: {', '.join(sorted(producer)) or 'nothing'}"
            raise PipelineConfigError(message)
        for key in stage.provides:
            if key.name in producer:
                raise PipelineConfigError(
                    f"artifact '{key}' would be written twice: by {producer[key.name]} "
                    f"and by stage '{stage.name}'"
                )
            producer[key.name] = f"stage '{stage.name}'"
