"""The text measurement interface and the registry of its providers.

    metrics = METRICS.get("fixed")()
    box = metrics.text("a", font="Inter", size=38, weight="regular", italic=False)
    box.width, box.ascent, box.descent      # reference pixels

A provider is chosen by name in ``pipeline.toml``
(``[options.resolve] metrics = "fixed"``); adding one is a new file with a
``@METRICS.register`` class.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar, Literal

from irpipe.core import PluginDefinitionError, Registry


@dataclass(frozen=True)
class TextBox:
    """The size of one line of text, in reference pixels.

    ``ascent`` is how far the text reaches above its baseline, ``descent``
    how far below it; the box is ``width`` by ``ascent + descent``.
    """

    width: float
    ascent: float
    descent: float

    @property
    def height(self) -> float:
        return self.ascent + self.descent


class TextMetrics(ABC):
    """Measures text the way one font engine draws it."""

    name: ClassVar[str]

    @abstractmethod
    def text(
        self,
        text: str,
        *,
        font: str,
        size: float,
        weight: Literal["regular", "bold"],
        italic: bool,
    ) -> TextBox:
        """The box of ``text`` set in ``font`` at ``size`` reference pixels."""


def _check_provider(cls: type[TextMetrics]) -> None:
    if not getattr(cls, "name", ""):
        raise PluginDefinitionError(f"text metrics provider {cls.__name__} needs a `name`")


METRICS: Registry[type[TextMetrics]] = Registry(
    "text metrics provider", key=lambda cls: cls.name, check=_check_provider
)
