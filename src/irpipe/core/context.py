"""What a stage can see while it runs.

``StageContext`` is a narrow window onto the run's artifacts. A stage may only
read the keys it declared in ``requires`` and only write the keys it declared
in ``provides``, each exactly once. Anything else raises ``StageContractError``
at once, so the declarations the pipeline uses to check the chain of stages
can never drift from what the stage's code really does.
"""

from collections.abc import Collection, Mapping
from types import MappingProxyType
from typing import Any

from irpipe.core.artifact import ArtifactKey
from irpipe.core.errors import StageContractError


class StageContext:
    """The artifacts and options one stage may use during one run."""

    def __init__(
        self,
        stage: str,
        artifacts: dict[str, object],
        readable: Collection[ArtifactKey[Any]],
        writable: Collection[ArtifactKey[Any]],
        options: Mapping[str, Any],
    ) -> None:
        self._stage = stage
        self._artifacts = artifacts  # shared store of the run; written only through write()
        self._readable = {key.name for key in readable}
        self._writable = {key.name for key in writable}
        self._written: set[str] = set()
        self._options = MappingProxyType(dict(options))

    @property
    def stage(self) -> str:
        """Name of the stage this context belongs to."""
        return self._stage

    @property
    def options(self) -> Mapping[str, Any]:
        """This stage's table from pipeline.toml (``[options.<stage>]``); read-only."""
        return self._options

    def read[T](self, key: ArtifactKey[T]) -> T:
        """Return the artifact ``key``; the stage must have declared it in ``requires``."""
        if key.name not in self._readable:
            raise StageContractError(
                f"stage '{self._stage}' read artifact '{key}' without declaring it in requires"
            )
        value = self._artifacts[key.name]
        if not isinstance(value, key.value_type):
            raise StageContractError(
                f"stage '{self._stage}' expected artifact '{key}' to be "
                f"{key.value_type.__name__}, found {type(value).__name__}"
            )
        return value

    def write[T](self, key: ArtifactKey[T], value: T) -> None:
        """Store ``value`` as artifact ``key``; declared in ``provides``, written once."""
        if key.name not in self._writable:
            raise StageContractError(
                f"stage '{self._stage}' wrote artifact '{key}' without declaring it in provides"
            )
        if key.name in self._written:
            raise StageContractError(f"stage '{self._stage}' wrote artifact '{key}' twice")
        if not isinstance(value, key.value_type):
            raise StageContractError(
                f"stage '{self._stage}' wrote a {type(value).__name__} to artifact '{key}', "
                f"which holds {key.value_type.__name__}"
            )
        self._artifacts[key.name] = value
        self._written.add(key.name)

    def unwritten(self) -> list[str]:
        """Names of the promised artifacts the stage has not written yet."""
        return sorted(self._writable - self._written)
