"""Stage declarations: a wrongly declared stage is refused when it registers."""

import pytest

from irpipe.core import (
    ArtifactKey,
    PluginDefinitionError,
    Stage,
    StageContext,
    make_stage_registry,
)

TEXT = ArtifactKey("text", str)
COUNT = ArtifactKey("count", int)


def test_a_complete_stage_registers_under_its_name() -> None:
    class Count(Stage):
        name = "count"
        requires = (TEXT,)
        provides = (COUNT,)

        def run(self, ctx: StageContext) -> None:
            ctx.write(COUNT, len(ctx.read(TEXT)))

    stages = make_stage_registry()
    stages.register(Count)
    assert stages.get("count") is Count


def test_a_stage_needs_a_name() -> None:
    class Nameless(Stage):
        def run(self, ctx: StageContext) -> None:
            pass

    with pytest.raises(PluginDefinitionError, match="needs a `name`"):
        make_stage_registry().register(Nameless)


def test_a_stage_must_implement_run() -> None:
    class Unfinished(Stage):  # run() is missing, so the class is still abstract
        name = "unfinished"

    with pytest.raises(PluginDefinitionError, match="does not implement run"):
        make_stage_registry().register(Unfinished)  # type: ignore[type-abstract]  # mypy too


def test_keys_must_be_a_tuple_of_artifact_keys() -> None:
    class Listy(Stage):
        name = "listy"
        # The deliberate mistake under test; mypy and ruff flag it too.
        requires = [TEXT]  # type: ignore[assignment]  # noqa: RUF012

        def run(self, ctx: StageContext) -> None:
            pass

    with pytest.raises(PluginDefinitionError, match="requires must be a tuple of ArtifactKey"):
        make_stage_registry().register(Listy)


def test_a_stage_cannot_overwrite_what_it_reads() -> None:
    class InPlace(Stage):
        name = "in_place"
        requires = (TEXT,)
        provides = (TEXT,)

        def run(self, ctx: StageContext) -> None:
            pass

    with pytest.raises(PluginDefinitionError, match="both requires and provides text"):
        make_stage_registry().register(InPlace)


def test_artifact_names_must_be_identifiers() -> None:
    with pytest.raises(ValueError, match="must be a Python identifier"):
        ArtifactKey("lir json", str)
