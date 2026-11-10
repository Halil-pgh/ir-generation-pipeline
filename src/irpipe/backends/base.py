"""The backend interface: what a backend can draw, and how it draws a LIR.

    @BACKENDS.register
    class SvgBackend(Backend):
        name = "svg"
        capabilities = frozenset({Capability.CUBIC, Capability.TEXT, ...})
        def render(self, lir, out_dir) -> Rendered: ...

A backend never lays out or resolves anything; the LIR is already final.
What it cannot draw is named in its ``capabilities``: the render stage
checks a LIR against them before drawing, and step 14 will lower such
features to simpler ones first.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar

from pydantic import ValidationError

from irpipe.core import (
    ISSUE_CODES,
    Issue,
    IssueCode,
    Origin,
    PipelineConfigError,
    PluginDefinitionError,
    Registry,
)
from irpipe.schema.base import StrictModel
from irpipe.schema.lir import CubicTo, Group, ImageItem, LIRDocument, MathItem, PathItem, QuadTo
from irpipe.schema.lir import TextItem as LIRText

E_CAPABILITY = ISSUE_CODES.register(
    IssueCode(
        "E-CAPABILITY", Origin.CAPABILITY, "the backend cannot draw a feature the picture uses"
    )
)
E_ENVIRONMENT = ISSUE_CODES.register(
    IssueCode("E-ENVIRONMENT", Origin.ENVIRONMENT, "a tool the pipeline needs is not installed")
)


class Capability(StrEnum):
    """A LIR feature some backends cannot draw. Lines, fills and opacity every backend can."""

    QUADRATIC = "quadratic"  # quadratic Bezier segments
    CUBIC = "cubic"  # cubic Bezier segments
    DASH = "dash"  # dashed strokes
    EVENODD = "evenodd"  # the even-odd fill rule
    TRANSFORM = "transform"  # group matrices other than the identity
    TEXT = "text"  # text items
    MATH = "math"  # typesetting TeX itself; formulas with glyph outlines need nothing
    IMAGE = "image"  # raster images


FEATURE_NAMES = {
    Capability.QUADRATIC: "quadratic curves",
    Capability.CUBIC: "cubic curves",
    Capability.DASH: "dashed lines",
    Capability.EVENODD: "even-odd fills",
    Capability.TRANSFORM: "group transforms",
    Capability.TEXT: "text",
    Capability.MATH: "formulas without glyph outlines",
    Capability.IMAGE: "images",
}


@dataclass(frozen=True)
class Rendered:
    """What one backend produced: the files it wrote and any problems it met."""

    files: tuple[Path, ...]
    issues: tuple[Issue, ...] = ()


class NoOptions(StrictModel):
    """A backend that takes no settings."""


class Backend(ABC):
    """Draws a LIR with one library.

    Settings come from ``[options.render.<name>]`` in ``pipeline.toml`` and
    are checked against ``options_model``; a misspelled setting is refused.
    """

    name: ClassVar[str]
    capabilities: ClassVar[frozenset[Capability]]
    options_model: ClassVar[type[StrictModel]] = NoOptions

    def __init__(self, options: Mapping[str, Any] | None = None) -> None:
        try:
            self.options = self.options_model.model_validate(dict(options or {}))
        except ValidationError as error:
            problems = "; ".join(
                f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors()
            )
            raise PipelineConfigError(f"backend '{self.name}' options: {problems}") from None

    @abstractmethod
    def render(self, lir: LIRDocument, out_dir: Path) -> Rendered:
        """Write this backend's files for ``lir`` into ``out_dir`` (which exists)."""


def _check_backend(cls: type[Backend]) -> None:
    if not getattr(cls, "name", ""):
        raise PluginDefinitionError(f"backend {cls.__name__} needs a `name`")
    if not isinstance(getattr(cls, "capabilities", None), frozenset):
        raise PluginDefinitionError(f"backend '{cls.name}' must list its capabilities")


BACKENDS: Registry[type[Backend]] = Registry(
    "backend", key=lambda cls: cls.name, check=_check_backend
)


def features_used(lir: LIRDocument) -> dict[Capability, list[str]]:
    """Every optional feature ``lir`` uses, with the ids of the groups that use it."""
    used: dict[Capability, list[str]] = {}

    def note(feature: Capability, gid: str) -> None:
        users = used.setdefault(feature, [])
        if gid not in users:
            users.append(gid)

    def visit(group: Group) -> None:
        if group.transform != (1, 0, 0, 1, 0, 0):
            note(Capability.TRANSFORM, group.id)
        for node in group.children:
            if isinstance(node, Group):
                visit(node)
            elif isinstance(node, PathItem):
                for segment in (s for sub in node.subpaths for s in sub.segments):
                    if isinstance(segment, CubicTo):
                        note(Capability.CUBIC, group.id)
                    elif isinstance(segment, QuadTo):
                        note(Capability.QUADRATIC, group.id)
                if node.stroke is not None and node.stroke.dash:
                    note(Capability.DASH, group.id)
                if node.fill is not None and node.fill.rule == "evenodd":
                    note(Capability.EVENODD, group.id)
            elif isinstance(node, LIRText):
                note(Capability.TEXT, group.id)
            elif isinstance(node, MathItem) and not node.glyphs:
                note(Capability.MATH, group.id)
            elif isinstance(node, ImageItem):
                note(Capability.IMAGE, group.id)

    for item in lir.items:
        visit(item)
    return used


def unsupported(lir: LIRDocument, backend: Backend) -> list[Issue]:
    """An E-CAPABILITY issue per feature ``lir`` uses that ``backend`` cannot draw.

    The message names the feature and the objects, never the backend: the
    agent fixes the IR, not the choice of backend (analysis §3).
    """
    return [
        E_CAPABILITY(
            f"{FEATURE_NAMES[feature]} cannot be drawn yet (used by {', '.join(users)})",
            objects=users,
        )
        for feature, users in features_used(lir).items()
        if feature not in backend.capabilities
    ]
