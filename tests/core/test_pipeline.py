"""Pipeline: building checks the chain of stages; running enforces each stage's contract.

The toy stages split a sentence into words and count them. They stand in for
real stages (validate, resolve...) that arrive in later steps. ``split``
reports an error and writes nothing for an empty sentence, the way validate
will for a broken IR.
"""

import pytest

from irpipe.core import (
    ArtifactKey,
    Issue,
    IssueCode,
    Origin,
    Pipeline,
    PipelineConfig,
    PipelineConfigError,
    Registry,
    Report,
    Severity,
    Stage,
    StageContext,
    StageContractError,
    StageFailedError,
    Status,
    UnknownPluginError,
    make_issue_code_registry,
    make_stage_registry,
)

TEXT = ArtifactKey("text", str, "a sentence")
WORDS = ArtifactKey("words", tuple, "the sentence split into words")
COUNT = ArtifactKey("count", int, "how many words")

SENTENCE = "a picture is worth a thousand words"

CODES = make_issue_code_registry()
E_NO_WORDS = CODES.register(IssueCode("E-NO-WORDS", Origin.IR, "the sentence has no words"))
W_SHORT = CODES.register(IssueCode("W-SHORT", Origin.IR, "the sentence is short"))
E_LONG_WORD = CODES.register(IssueCode("E-LONG-WORD", Origin.IR, "a word is too long"))


class Split(Stage):
    name = "split"
    requires = (TEXT,)
    provides = (WORDS,)

    def run(self, ctx: StageContext) -> None:
        words = tuple(ctx.read(TEXT).split())
        if not words:
            ctx.report(E_NO_WORDS("the text is empty", path="text", hint="write a sentence"))
            return  # nothing to write, and the error says why
        if len(words) < 3:
            ctx.report(W_SHORT(f"only {len(words)} words"))
        ctx.write(WORDS, words)


class Lint(Stage):
    """Like a lint check: reports problems but writes nothing, so it never stops the run."""

    name = "lint"
    requires = (WORDS,)

    def run(self, ctx: StageContext) -> None:
        words = ctx.read(WORDS)
        for k, word in enumerate(words):
            if len(word) > 7:
                ctx.report(E_LONG_WORD(f"'{word}' is too long", path=f"words[{k}]"))


class Count(Stage):
    """Counts words; the option ``min_length`` skips shorter ones."""

    name = "count"
    requires = (WORDS,)
    provides = (COUNT,)

    def run(self, ctx: StageContext) -> None:
        min_length = int(ctx.options.get("min_length", 0))
        ctx.write(COUNT, sum(1 for word in ctx.read(WORDS) if len(word) >= min_length))


@pytest.fixture
def registry() -> Registry[type[Stage]]:
    stages = make_stage_registry()
    stages.register(Split)
    stages.register(Count)
    return stages


# Building: the chain is checked before anything runs.


def test_stages_run_in_order_and_share_artifacts(registry: Registry[type[Stage]]) -> None:
    pipeline = Pipeline.build(["split", "count"], inputs=[TEXT], registry=registry)
    result = pipeline.run({TEXT: SENTENCE})
    assert result.get(WORDS) == ("a", "picture", "is", "worth", "a", "thousand", "words")
    assert result.get(COUNT) == 7
    assert [run.name for run in result.stages] == ["split", "count"]


def test_removing_a_producer_is_refused_before_anything_runs(
    registry: Registry[type[Stage]],
) -> None:
    with pytest.raises(PipelineConfigError, match="stage 'count' requires artifact 'words'"):
        Pipeline.build(["count"], inputs=[TEXT], registry=registry)


def test_wrong_order_names_the_stage_that_runs_too_late(registry: Registry[type[Stage]]) -> None:
    with pytest.raises(PipelineConfigError, match="'split' provides it but runs later"):
        Pipeline.build(["count", "split"], inputs=[TEXT], registry=registry)


def test_two_producers_of_one_artifact_are_refused(registry: Registry[type[Stage]]) -> None:
    class SplitAgain(Split):
        name = "split_again"

    registry.register(SplitAgain)
    with pytest.raises(PipelineConfigError, match="'words' would be written twice"):
        Pipeline.build(["split", "split_again"], inputs=[TEXT], registry=registry)


def test_an_input_cannot_be_overwritten() -> None:
    class Rewrite(Stage):
        name = "rewrite"
        provides = (TEXT,)

        def run(self, ctx: StageContext) -> None:
            ctx.write(TEXT, "new")

    with pytest.raises(PipelineConfigError, match="written twice: by the inputs"):
        Pipeline([Rewrite()], inputs=[TEXT])


def test_a_stage_listed_twice_is_refused(registry: Registry[type[Stage]]) -> None:
    with pytest.raises(PipelineConfigError, match="appears twice"):
        Pipeline.build(["split", "split"], inputs=[TEXT], registry=registry)


def test_an_unknown_stage_name_suggests_the_close_one(registry: Registry[type[Stage]]) -> None:
    with pytest.raises(UnknownPluginError, match="did you mean 'split'"):
        Pipeline.build(["spilt"], inputs=[TEXT], registry=registry)


# Options: [options.<stage>] in pipeline.toml.


def test_options_reach_their_stage(registry: Registry[type[Stage]]) -> None:
    pipeline = Pipeline.build(
        ["split", "count"], inputs=[TEXT], options={"count": {"min_length": 5}}, registry=registry
    )
    assert pipeline.run({TEXT: SENTENCE}).get(COUNT) == 4  # picture, worth, thousand, words


def test_a_switched_off_stage_may_keep_its_options(registry: Registry[type[Stage]]) -> None:
    pipeline = Pipeline.build(
        ["split"], inputs=[TEXT], options={"count": {"min_length": 5}}, registry=registry
    )
    assert pipeline.stage_names == ("split",)


def test_options_for_an_unregistered_name_are_a_typo(registry: Registry[type[Stage]]) -> None:
    with pytest.raises(UnknownPluginError, match="did you mean 'count'"):
        Pipeline.build(["split"], inputs=[TEXT], options={"cuont": {}}, registry=registry)


def test_from_config_builds_the_configured_chain(registry: Registry[type[Stage]]) -> None:
    config = PipelineConfig.model_validate(
        {"pipeline": {"stages": ["split", "count"]}, "options": {"count": {"min_length": 5}}}
    )
    pipeline = Pipeline.from_config(config, inputs=[TEXT], registry=registry)
    assert pipeline.run({TEXT: SENTENCE}).get(COUNT) == 4


# Running: inputs and each stage's declared reads and writes are enforced.


def test_run_needs_exactly_the_declared_inputs(registry: Registry[type[Stage]]) -> None:
    pipeline = Pipeline.build(["split"], inputs=[TEXT], registry=registry)
    with pytest.raises(PipelineConfigError, match="needs exactly the inputs"):
        pipeline.run({})


def test_run_checks_input_types(registry: Registry[type[Stage]]) -> None:
    pipeline = Pipeline.build(["split"], inputs=[TEXT], registry=registry)
    with pytest.raises(PipelineConfigError, match="input 'text' must be str"):
        pipeline.run({TEXT: 42})


def test_reading_an_undeclared_artifact_fails() -> None:
    class Peek(Stage):
        name = "peek"
        provides = (COUNT,)

        def run(self, ctx: StageContext) -> None:
            ctx.write(COUNT, len(ctx.read(TEXT)))

    with pytest.raises(StageContractError, match="read artifact 'text' without declaring"):
        Pipeline([Peek()], inputs=[TEXT]).run({TEXT: SENTENCE})


def test_writing_an_undeclared_artifact_fails() -> None:
    class Leak(Stage):
        name = "leak"
        requires = (TEXT,)

        def run(self, ctx: StageContext) -> None:
            ctx.write(COUNT, 1)

    with pytest.raises(StageContractError, match="wrote artifact 'count' without declaring"):
        Pipeline([Leak()], inputs=[TEXT]).run({TEXT: SENTENCE})


def test_a_promised_artifact_must_be_written() -> None:
    class Lazy(Stage):
        name = "lazy"
        requires = (TEXT,)
        provides = (COUNT,)

        def run(self, ctx: StageContext) -> None:
            pass

    with pytest.raises(
        StageContractError, match="'lazy' finished without writing count and reported no error"
    ):
        Pipeline([Lazy()], inputs=[TEXT]).run({TEXT: SENTENCE})


def test_an_artifact_is_written_once() -> None:
    class Twice(Stage):
        name = "twice"
        provides = (COUNT,)

        def run(self, ctx: StageContext) -> None:
            ctx.write(COUNT, 1)
            ctx.write(COUNT, 2)

    with pytest.raises(StageContractError, match="wrote artifact 'count' twice"):
        Pipeline([Twice()], inputs=[]).run({})


def test_a_written_value_must_have_the_declared_type() -> None:
    class WrongType(Stage):
        name = "wrong_type"
        provides = (COUNT,)

        def run(self, ctx: StageContext) -> None:
            ctx.write(COUNT, "three")  # type: ignore[misc]  # mypy catches this too

    with pytest.raises(StageContractError, match="wrote a str to artifact 'count'"):
        Pipeline([WrongType()], inputs=[]).run({})


def test_an_unexpected_exception_names_its_stage() -> None:
    class Boom(Stage):
        name = "boom"

        def run(self, ctx: StageContext) -> None:
            raise ValueError("no luck")

    with pytest.raises(StageFailedError, match="stage 'boom' failed: ValueError: no luck") as err:
        Pipeline([Boom()], inputs=[]).run({})
    assert isinstance(err.value.__cause__, ValueError)


# Issues: problems in the picture are reported, and a stage that cannot go on stops the run.


def test_reported_issues_are_collected_with_their_stage() -> None:
    result = Pipeline([Split(), Count()], inputs=[TEXT], codes=CODES).run({TEXT: "two words"})
    (issue,) = result.issues
    assert (issue.code, issue.stage, issue.message) == ("W-SHORT", "split", "only 2 words")
    assert result.stopped_at is None
    assert result.get(COUNT) == 2  # a warning does not stop anything
    assert Report.build(result.issues, codes=CODES).status is Status.NOT_READY


def test_an_error_instead_of_the_output_stops_the_run() -> None:
    result = Pipeline([Split(), Count()], inputs=[TEXT], codes=CODES).run({TEXT: "   "})
    assert result.stopped_at == "split"
    assert [run.name for run in result.stages] == ["split"]  # count never ran
    assert [issue.code for issue in result.issues] == ["E-NO-WORDS"]
    with pytest.raises(KeyError, match="stopped after stage 'split'"):
        result.get(COUNT)
    report = Report.build(result.issues, stopped_at=result.stopped_at, codes=CODES)
    assert report.headline == "STOPPED at 'split' (1 error, 0 warnings)"


def test_an_error_next_to_the_output_does_not_stop_the_run() -> None:
    pipeline = Pipeline([Split(), Lint(), Count()], inputs=[TEXT], codes=CODES)
    result = pipeline.run({TEXT: SENTENCE})
    assert result.stopped_at is None
    assert result.get(COUNT) == 7  # count ran after lint's error
    (issue,) = result.issues
    assert (issue.code, issue.severity, issue.stage) == ("E-LONG-WORD", Severity.ERROR, "lint")


def test_a_warning_is_not_a_reason_to_skip_the_output() -> None:
    class Shrug(Stage):
        name = "shrug"
        provides = (COUNT,)

        def run(self, ctx: StageContext) -> None:
            ctx.report(W_SHORT("too short to count"))

    with pytest.raises(StageContractError, match="reported no error that says why"):
        Pipeline([Shrug()], inputs=[], codes=CODES).run({})


def test_only_registered_codes_can_be_reported() -> None:
    e_no_word = IssueCode("E-NO-WORD", Origin.IR, "a code nobody registered")

    class Stray(Stage):
        name = "stray"

        def run(self, ctx: StageContext) -> None:
            ctx.report(e_no_word("nothing here"))

    with pytest.raises(StageContractError, match="not a registered issue code; did you mean"):
        Pipeline([Stray()], inputs=[], codes=CODES).run({})


def test_an_issue_keeps_the_origin_of_its_code() -> None:
    class Blame(Stage):
        name = "blame"

        def run(self, ctx: StageContext) -> None:
            ctx.report(
                Issue(
                    code="E-NO-WORDS",
                    severity=Severity.ERROR,
                    origin=Origin.ENVIRONMENT,
                    message="blaming the machine",
                )
            )

    with pytest.raises(StageContractError, match="defined with origin ir"):
        Pipeline([Blame()], inputs=[], codes=CODES).run({})
