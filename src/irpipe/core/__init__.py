"""The pipeline machinery, independent of pictures: stages, artifacts, registries, config.

Everything a stage author or a pipeline user needs is importable from here:

    from irpipe.core import ArtifactKey, Pipeline, Stage, StageContext, STAGES

Module map:
    artifact.py  ArtifactKey: the name and type of data passed between stages
    stage.py     Stage: the interface of one step; STAGES: the stage registry
    context.py   StageContext: what a running stage may read and write
    pipeline.py  Pipeline: checks the chain of stages and runs it
    registry.py  Registry: the one pattern behind every kind of plugin
    plugins.py   load_plugins: imports plugin packages so they register
    config.py    load_config: reads pipeline.toml
    errors.py    the exceptions for a wrongly set up or wrongly written pipeline
"""

from irpipe.core.artifact import ArtifactKey
from irpipe.core.config import PipelineConfig, load_config
from irpipe.core.context import StageContext
from irpipe.core.errors import (
    DuplicatePluginError,
    PipelineConfigError,
    PipelineError,
    PluginDefinitionError,
    PluginLoadError,
    StageContractError,
    StageFailedError,
    UnknownPluginError,
)
from irpipe.core.pipeline import Pipeline, RunResult, StageRun
from irpipe.core.plugins import load_plugins
from irpipe.core.registry import Registry
from irpipe.core.stage import STAGES, Stage, check_stage_class, make_stage_registry

__all__ = [
    "STAGES",
    "ArtifactKey",
    "DuplicatePluginError",
    "Pipeline",
    "PipelineConfig",
    "PipelineConfigError",
    "PipelineError",
    "PluginDefinitionError",
    "PluginLoadError",
    "Registry",
    "RunResult",
    "Stage",
    "StageContext",
    "StageContractError",
    "StageFailedError",
    "StageRun",
    "UnknownPluginError",
    "check_stage_class",
    "load_config",
    "load_plugins",
    "make_stage_registry",
]
