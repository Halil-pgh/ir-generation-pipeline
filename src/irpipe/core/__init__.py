"""The pipeline machinery, independent of pictures: stages, artifacts, issues, registries.

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
    issues.py    Issue, IssueCode, ISSUE_CODES: problems found in a picture
    allow.py     Allow: accepting an issue on purpose, with a reason
    report.py    Report: READY or not, with every issue of the run
"""

from irpipe.core.allow import (
    E_ALLOW,
    MIN_REASON_WORDS,
    Allow,
    Covers,
    apply_allows,
    check_allows,
    covers_by_name,
)
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
from irpipe.core.issues import (
    ISSUE_CODES,
    Issue,
    IssueCode,
    Origin,
    Severity,
    make_issue_code_registry,
    severity_of,
)
from irpipe.core.pipeline import Pipeline, RunResult, StageRun
from irpipe.core.plugins import load_plugins
from irpipe.core.registry import Registry
from irpipe.core.report import Report, Status
from irpipe.core.stage import STAGES, Stage, check_stage_class, make_stage_registry

__all__ = [
    "E_ALLOW",
    "ISSUE_CODES",
    "MIN_REASON_WORDS",
    "STAGES",
    "Allow",
    "ArtifactKey",
    "Covers",
    "DuplicatePluginError",
    "Issue",
    "IssueCode",
    "Origin",
    "Pipeline",
    "PipelineConfig",
    "PipelineConfigError",
    "PipelineError",
    "PluginDefinitionError",
    "PluginLoadError",
    "Registry",
    "Report",
    "RunResult",
    "Severity",
    "Stage",
    "StageContext",
    "StageContractError",
    "StageFailedError",
    "StageRun",
    "Status",
    "UnknownPluginError",
    "apply_allows",
    "check_allows",
    "check_stage_class",
    "covers_by_name",
    "load_config",
    "load_plugins",
    "make_issue_code_registry",
    "make_stage_registry",
    "severity_of",
]
