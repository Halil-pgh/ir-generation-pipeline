"""Every way the pipeline machinery itself can fail.

These exceptions mean the pipeline is set up or written wrongly: a misspelled
stage, a broken chain of stages, a stage that breaks its contract. They are
for the people building the pipeline. Problems in a picture (an overlap, an
unknown reference in the IR) are not exceptions; they are reported as issues
and never raise.
"""


class PipelineError(Exception):
    """Base class: something is wrong with how the pipeline is set up or written."""


class PipelineConfigError(PipelineError):
    """The configuration names something unknown or builds a broken chain of stages."""


class UnknownPluginError(PipelineConfigError):
    """A name is not in its registry, for example a misspelled stage in pipeline.toml."""


class DuplicatePluginError(PipelineError):
    """Two different plugins of the same kind were registered under one name."""


class PluginDefinitionError(PipelineError):
    """A plugin class is declared wrongly: no name, still abstract, or contradictory keys."""


class PluginLoadError(PipelineError):
    """A plugin module could not be imported."""


class StageContractError(PipelineError):
    """A stage read or wrote an artifact it did not declare, or skipped one it promised."""


class StageFailedError(PipelineError):
    """A stage raised an unexpected exception; the original is chained as ``__cause__``."""

    def __init__(self, stage: str, cause: BaseException) -> None:
        super().__init__(f"stage '{stage}' failed: {type(cause).__name__}: {cause}")
        self.stage = stage
