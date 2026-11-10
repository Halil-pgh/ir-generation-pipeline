"""The backend interface: capabilities, the feature check, settings and the registry."""

from typing import Any, ClassVar

import pytest

from irpipe.backends.base import (
    BACKENDS,
    Backend,
    Capability,
    Rendered,
    features_used,
    unsupported,
)
from irpipe.core import PipelineConfigError, PluginDefinitionError
from irpipe.schema.base import StrictModel
from irpipe.schema.lir import LIRDocument

CUBIC = {"start": [0, 0], "segments": [{"cubic": [[0, 1], [1, 1], [1, 0]]}]}
MATH = {
    "type": "math",
    "tex": "x^2",
    "size": 42,
    "color": "#FFFFFF",
    "at": [0, 0],
    "anchor": "center",
    "box": [-0.2, -0.1, 0.2, 0.1],
    "baseline": -0.05,
}


class LinesOnly(Backend):
    """A backend that draws nothing but straight, solid lines."""

    name = "lines_only"
    capabilities: ClassVar[frozenset[Capability]] = frozenset()

    def render(self, lir: LIRDocument, out_dir: Any) -> Rendered:
        return Rendered(())


def test_features_are_listed_with_the_groups_that_use_them(
    make_lir: Any, group: Any, line: dict[str, Any]
) -> None:
    dashed = {**line, "stroke": {"color": "#FFFFFF", "width": 4, "dash": [8, 4]}}
    curve = {**line, "subpaths": [CUBIC]}
    lir = make_lir(
        group("a", dashed),
        group("b", curve, transform=[0, 1, -1, 0, 0, 0]),
        group("f", MATH),
    )
    assert features_used(lir) == {
        Capability.DASH: ["a"],
        Capability.TRANSFORM: ["b"],
        Capability.CUBIC: ["b"],
        Capability.MATH: ["f"],
    }


def test_a_formula_with_glyph_outlines_needs_no_tex(make_lir: Any, group: Any) -> None:
    lir = make_lir(group("f", {**MATH, "glyphs": [CUBIC]}))
    assert Capability.MATH not in features_used(lir)


def test_what_a_backend_cannot_draw_is_named_without_the_backend(
    make_lir: Any, group: Any, line: dict[str, Any]
) -> None:
    lir = make_lir(group("a", {**line, "subpaths": [CUBIC]}))
    (issue,) = unsupported(lir, LinesOnly())
    assert (issue.code, issue.origin) == ("E-CAPABILITY", "capability")
    assert issue.message == "cubic curves cannot be drawn yet (used by a)"
    assert "lines_only" not in issue.message
    assert issue.objects == ("a",)


def test_a_misspelled_setting_is_refused() -> None:
    class Tidy(StrictModel):
        png: bool = True

    class WithSettings(LinesOnly):
        name = "with_settings"
        options_model = Tidy

    WithSettings({"png": False})
    with pytest.raises(PipelineConfigError, match="backend 'with_settings' options: pgn"):
        WithSettings({"pgn": False})


def test_a_backend_must_list_its_capabilities() -> None:
    class Vague(LinesOnly):
        name = "vague"
        capabilities = None  # type: ignore[assignment]

    with pytest.raises(PluginDefinitionError, match="must list its capabilities"):
        BACKENDS.register(Vague)


def test_the_svg_backend_is_registered() -> None:
    import irpipe.backends.svg  # noqa: F401  (registers on import)

    assert BACKENDS.get("svg").name == "svg"
