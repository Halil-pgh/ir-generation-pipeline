"""The interface every pipeline stage implements, and the stage registry.

A stage does one job. It reads the artifacts it ``requires``, writes the
artifacts it ``provides``, and touches nothing else. Because stages talk only
through artifacts, any stage can be added, removed or replaced by editing
``pipeline.toml``; the pipeline checks the whole chain before running anything.

    @STAGES.register
    class Validate(Stage):
        name = "validate"
        requires = (IR,)
        provides = (IR_VALID,)

        def run(self, ctx: StageContext) -> None:
            ir = ctx.read(IR)
            ...
            ctx.write(IR_VALID, checked)

Stages hold no state between runs: the pipeline creates each one with no
arguments, and per-stage settings arrive through ``ctx.options``.
"""

import inspect
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from irpipe.core.artifact import ArtifactKey
from irpipe.core.context import StageContext
from irpipe.core.errors import PluginDefinitionError
from irpipe.core.registry import Registry


class Stage(ABC):
    """One step of the pipeline. Subclasses set the three class attributes and ``run``."""

    name: ClassVar[str]
    """Name used in pipeline.toml; a Python identifier such as ``"validate"``."""

    requires: ClassVar[tuple[ArtifactKey[Any], ...]] = ()
    """Artifacts this stage reads. Each must come from the inputs or an earlier stage."""

    provides: ClassVar[tuple[ArtifactKey[Any], ...]] = ()
    """Artifacts this stage writes, each exactly once. No other stage may write them."""

    @abstractmethod
    def run(self, ctx: StageContext) -> None:
        """Do the stage's job: read what it requires from ``ctx``, write what it provides."""


def check_stage_class(cls: type[Stage]) -> None:
    """Reject a stage class whose declaration is incomplete or contradictory."""
    if not (inspect.isclass(cls) and issubclass(cls, Stage)):
        raise PluginDefinitionError(f"{cls!r} is not a subclass of Stage")
    label = cls.__qualname__
    name = getattr(cls, "name", None)
    if not isinstance(name, str) or not name.isidentifier():
        raise PluginDefinitionError(f"stage {label} needs a `name` that is a Python identifier")
    if inspect.isabstract(cls):
        raise PluginDefinitionError(f"stage '{name}' ({label}) does not implement run()")
    for field in ("requires", "provides"):
        keys = getattr(cls, field)
        if not isinstance(keys, tuple) or not all(isinstance(k, ArtifactKey) for k in keys):
            raise PluginDefinitionError(f"stage '{name}': {field} must be a tuple of ArtifactKey")
        names = [k.name for k in keys]
        if len(names) != len(set(names)):
            raise PluginDefinitionError(f"stage '{name}' lists an artifact twice in {field}")
    both = {k.name for k in cls.requires} & {k.name for k in cls.provides}
    if both:
        raise PluginDefinitionError(
            f"stage '{name}' both requires and provides {', '.join(sorted(both))}; "
            "artifacts are never overwritten, so provide a new one instead"
        )


def make_stage_registry() -> Registry[type[Stage]]:
    """A new, empty stage registry (tests use their own; the program uses ``STAGES``)."""
    return Registry("stage", key=lambda cls: cls.name, check=check_stage_class)


STAGES: Registry[type[Stage]] = make_stage_registry()
"""The registry the built-in stages join and pipeline.toml names refer to."""
