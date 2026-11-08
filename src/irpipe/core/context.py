"""What a stage can see while it runs.

``StageContext`` is a narrow window onto the run's artifacts. A stage may only
read the keys it declared in ``requires`` and only write the keys it declared
in ``provides``, each exactly once. Anything else raises ``StageContractError``
at once, so the declarations the pipeline uses to check the chain of stages
can never drift from what the stage's code really does.

Problems the stage finds in the picture go through ``report``; their codes
must be registered (core/issues.py).
"""

from collections.abc import Collection, Mapping
from types import MappingProxyType
from typing import Any

from irpipe.core.artifact import ArtifactKey
from irpipe.core.errors import StageContractError
from irpipe.core.issues import Issue, IssueCode
from irpipe.core.registry import Registry


class StageContext:
    """The artifacts, options and issue codes one stage may use during one run."""

    def __init__(
        self,
        stage: str,
        artifacts: dict[str, object],
        readable: Collection[ArtifactKey[Any]],
        writable: Collection[ArtifactKey[Any]],
        options: Mapping[str, Any],
        codes: Registry[IssueCode],
    ) -> None:
        self._stage = stage
        self._artifacts = artifacts  # shared store of the run; written only through write()
        self._readable = {key.name for key in readable}
        self._writable = {key.name for key in writable}
        self._written: set[str] = set()
        self._options = MappingProxyType(dict(options))
        self._codes = codes
        self._issues: list[Issue] = []

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

    def report(self, *issues: Issue) -> None:
        """Record problems found in the picture; each code must be a registered one."""
        for issue in issues:
            if issue.code not in self._codes:
                close = self._codes.closest(issue.code)
                raise StageContractError(
                    f"stage '{self._stage}' reported {issue.code}, which is not a registered "
                    "issue code" + (f"; did you mean {close}?" if close else "")
                )
            defined = self._codes.get(issue.code).origin
            if issue.origin != defined:
                raise StageContractError(
                    f"stage '{self._stage}' reported {issue.code} with origin {issue.origin}, "
                    f"but the code is defined with origin {defined}"
                )
            self._issues.append(issue.model_copy(update={"stage": self._stage}))

    @property
    def issues(self) -> tuple[Issue, ...]:
        """The issues this stage has reported so far, each marked with the stage's name."""
        return tuple(self._issues)

    def unwritten(self) -> list[str]:
        """Names of the promised artifacts the stage has not written yet."""
        return sorted(self._writable - self._written)
