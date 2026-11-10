"""The interface every check implements, and the check registry.

A check reads the drawn picture (the LIR, with the IR at hand for what the
agent meant) and returns issues in IR terms: the object's id and its JSON
path, never a LIR index (analysis §3). One check, one file, one or more
issue codes registered next to it.

    @CHECKS.register
    class TextSize(Check):
        name = "text_size"
        codes = (W_SMALL_TEXT,)
        options_model = TextSizeOptions

        def check(self, picture: Picture) -> Iterable[Issue]:
            ...

Which checks run, and their settings, is up to ``pipeline.toml``: the list
in ``[options.check] checks`` and a table ``[options.check.<name>]`` each.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from typing import Any, ClassVar

from pydantic import ValidationError

from irpipe.checks.picture import Picture
from irpipe.core import Issue, IssueCode, Registry
from irpipe.core.errors import PipelineConfigError, PluginDefinitionError
from irpipe.schema.base import StrictModel


class NoOptions(StrictModel):
    """A check that takes no settings."""


class Check(ABC):
    """One readability or composition check over the drawn picture."""

    name: ClassVar[str]
    codes: ClassVar[tuple[IssueCode, ...]]
    """The issue codes this check reports, registered in ISSUE_CODES."""
    options_model: ClassVar[type[StrictModel]] = NoOptions

    def __init__(self, options: Mapping[str, Any] | None = None) -> None:
        try:
            self.options: Any = self.options_model.model_validate(dict(options or {}))
        except ValidationError as error:
            problems = "; ".join(
                f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors()
            )
            raise PipelineConfigError(f"check '{self.name}' options: {problems}") from None

    @abstractmethod
    def check(self, picture: Picture) -> Iterable[Issue]:
        """Every problem this check finds in ``picture``."""


def _check_check(cls: type[Check]) -> None:
    if not getattr(cls, "name", ""):
        raise PluginDefinitionError(f"check {cls.__name__} needs a `name`")
    if not getattr(cls, "codes", ()):
        raise PluginDefinitionError(f"check '{cls.name}' must list the issue codes it reports")


CHECKS: Registry[type[Check]] = Registry("check", key=lambda cls: cls.name, check=_check_check)
