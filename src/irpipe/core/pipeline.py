"""Builds a chain of stages, checks that the chain is complete, and runs it.

This is where plug-and-play is made safe. Creating a ``Pipeline`` walks the
stages in order and refuses to start when

- a stage requires an artifact that neither the inputs nor an earlier stage
  provides (typically: the stage that made it was removed or moved later), or
- two producers would write the same artifact.

Every error names the stage and the artifact. While running, each stage gets a
``StageContext`` that enforces its declared reads and writes.

A stage either writes everything it promised, or reports at least one error
that says why it could not. In the second case the run stops after that stage
(``RunResult.stopped_at``), since the stages after it would lack their input.
A stage that reports errors but still writes its outputs (a lint check, say)
does not stop the run, so a picture with problems is still drawn.

    pipeline = Pipeline.build(["validate", "resolve"], inputs=[IR])
    result = pipeline.run({IR: ir_document})
    lir = result.get(LIR)
    report = Report.build(result.issues, stopped_at=result.stopped_at)
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
from irpipe.core.issues import ISSUE_CODES, Issue, IssueCode, Severity
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
    """Everything a run produced.

    ``stages`` lists the stages that ran, in order; ``issues`` every issue they
    reported; ``stopped_at`` the stage the run stopped after, or ``None`` when
    every stage ran.
    """

    artifacts: Mapping[str, object]
    stages: tuple[StageRun, ...]
    issues: tuple[Issue, ...] = ()
    stopped_at: str | None = None

    def get[T](self, key: ArtifactKey[T]) -> T:
        """The artifact ``key``, type-checked."""
        if key.name not in self.artifacts:
            message = f"the run produced no artifact '{key}'"
            if self.stopped_at is not None:
                message += f" (it stopped after stage '{self.stopped_at}')"
            raise KeyError(message)
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
        codes: Registry[IssueCode] = ISSUE_CODES,
    ) -> None:
        self._stages = tuple(stages)
        self._inputs = tuple(inputs)
        self._options = {name: dict(values) for name, values in (options or {}).items()}
        self._codes = codes
        _check_chain(self._stages, self._inputs)

    @classmethod
    def build(
        cls,
        stage_names: Sequence[str],
        *,
        inputs: Iterable[ArtifactKey[Any]],
        options: StageOptions | None = None,
        registry: Registry[type[Stage]] = STAGES,
        codes: Registry[IssueCode] = ISSUE_CODES,
    ) -> "Pipeline":
        """Look the stages up by name and create the pipeline.

        Options may name stages that are registered but not in this pipeline
        (a stage switched off keeps its settings); a name that is not
        registered at all is treated as a typo and rejected.
        """
        for name in options or {}:
            registry.get(name)  # raises UnknownPluginError, with a "did you mean"
        stages = [registry.get(name)() for name in stage_names]
        return cls(stages, inputs, options, codes)

    @classmethod
    def from_config(
        cls,
        config: PipelineConfig,
        *,
        inputs: Iterable[ArtifactKey[Any]],
        registry: Registry[type[Stage]] = STAGES,
        codes: Registry[IssueCode] = ISSUE_CODES,
    ) -> "Pipeline":
        """Import the configured plugin packages, then build the configured stages."""
        load_plugins(config.pipeline.plugins)
        return cls.build(
            config.pipeline.stages,
            inputs=inputs,
            options=config.options,
            registry=registry,
            codes=codes,
        )

    @property
    def stage_names(self) -> tuple[str, ...]:
        return tuple(stage.name for stage in self._stages)

    @property
    def inputs(self) -> tuple[ArtifactKey[Any], ...]:
        return self._inputs

    def run(self, inputs: Mapping[ArtifactKey[Any], object]) -> RunResult:
        """Run the stages in order; stop after a stage that could not write its outputs."""
        artifacts = self._take_inputs(inputs)
        runs: list[StageRun] = []
        issues: list[Issue] = []
        for stage in self._stages:
            ctx = StageContext(
                stage.name,
                artifacts,
                readable=stage.requires,
                writable=stage.provides,
                options=self._options.get(stage.name, {}),
                codes=self._codes,
            )
            started = time.perf_counter()
            try:
                stage.run(ctx)
            except PipelineError:
                raise
            except Exception as exc:
                raise StageFailedError(stage.name, exc) from exc
            runs.append(StageRun(stage.name, time.perf_counter() - started))
            issues.extend(ctx.issues)
            missing = ctx.unwritten()
            if not missing:
                continue
            if not any(issue.severity is Severity.ERROR for issue in ctx.issues):
                raise StageContractError(
                    f"stage '{stage.name}' finished without writing {', '.join(missing)} "
                    "and reported no error that says why"
                )
            return RunResult(
                MappingProxyType(artifacts), tuple(runs), tuple(issues), stopped_at=stage.name
            )
        return RunResult(MappingProxyType(artifacts), tuple(runs), tuple(issues))

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
