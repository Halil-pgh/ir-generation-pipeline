"""The text measurement interface and the registry of its providers.

    metrics = METRICS.get("pango")()
    box = metrics.text("a", font="Inter", size=38, weight="regular", italic=False)
    box.width, box.ascent, box.descent      # reference pixels
    formula = metrics.math(r"\\frac{a}{b}", math_font="latin-modern", size=42)
    formula.outlines                         # glyph outlines, reference pixels

A provider is chosen by name in ``pipeline.toml``
(``[options.measure] metrics = "pango"``); adding one is a new file with a
``@METRICS.register`` class.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar, Literal

from irpipe.core import PluginDefinitionError, Registry
from irpipe.metrics.svgpath import Subpath


@dataclass(frozen=True)
class TextBox:
    """The size of one line of text, in reference pixels.

    ``ascent`` is how far the box reaches above its baseline, ``descent`` how
    far below it; the box is ``width`` by ``ascent + descent``.
    """

    width: float
    ascent: float
    descent: float

    @property
    def height(self) -> float:
        return self.ascent + self.descent


@dataclass(frozen=True)
class MathBox(TextBox):
    """A typeset formula: its box, and its glyph outlines.

    Outlines are in reference pixels, y up, with the origin at the left end
    of the baseline, so they are placed exactly like the box.
    """

    outlines: tuple[Subpath, ...] = ()


class TextMetrics(ABC):
    """Measures text and formulas the way one backend's engines draw them."""

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

    @abstractmethod
    def math(self, tex: str, *, math_font: str, size: float) -> MathBox:
        """The box and outlines of ``tex``; raises TexError when it cannot be set."""

    def missing_fonts(self, families: Iterable[str]) -> list[str]:
        """The families that are not installed, so text would be set in a substitute."""
        return []


def _check_provider(cls: type[TextMetrics]) -> None:
    if not getattr(cls, "name", ""):
        raise PluginDefinitionError(f"text metrics provider {cls.__name__} needs a `name`")


METRICS: Registry[type[TextMetrics]] = Registry(
    "text metrics provider", key=lambda cls: cls.name, check=_check_provider
)
