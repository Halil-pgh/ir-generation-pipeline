"""Issue codes: defined once, severity read from the letter, built by calling the code."""

import pytest
from pydantic import ValidationError

from irpipe.core import (
    ISSUE_CODES,
    DuplicatePluginError,
    Issue,
    IssueCode,
    Origin,
    Severity,
    make_issue_code_registry,
)

E_TOY = IssueCode("E-TOY", Origin.IR, "a toy error")
W_TOY_OVERLAP = IssueCode("W-TOY-OVERLAP", Origin.IR, "two toys overlap", allowable=True)


def test_the_letter_of_a_code_is_its_severity() -> None:
    assert E_TOY.severity is Severity.ERROR
    assert W_TOY_OVERLAP.severity is Severity.WARNING


@pytest.mark.parametrize("code", ["TOY", "e-toy", "X-TOY", "E-", "E_TOY", "E-TOY-"])
def test_a_malformed_code_is_refused(code: str) -> None:
    with pytest.raises(ValueError, match="looks like E-NAME or W-NAME"):
        IssueCode(code, Origin.IR, "malformed")


def test_an_error_is_never_allowable() -> None:
    with pytest.raises(ValueError, match="an error always has to be fixed"):
        IssueCode("E-TOY-CUT", Origin.IR, "a toy is cut off", allowable=True)


def test_only_warnings_of_the_ir_can_be_allowable() -> None:
    with pytest.raises(ValueError, match="only warnings that originate in the IR"):
        IssueCode("W-SLOW-FONT", Origin.ENVIRONMENT, "the font loads slowly", allowable=True)


def test_calling_a_code_builds_an_issue_of_that_kind() -> None:
    issue = W_TOY_OVERLAP(
        "the ball covers the box", path="objects[1]", objects=["ball", "box"], hint="move it"
    )
    assert issue.code == "W-TOY-OVERLAP"
    assert issue.severity is Severity.WARNING
    assert issue.origin is Origin.IR
    assert issue.objects == ("ball", "box")
    assert issue.is_open


def test_an_issue_cannot_contradict_its_code() -> None:
    with pytest.raises(ValidationError, match="E-TOY is an error, not a warning"):
        Issue(code="E-TOY", severity=Severity.WARNING, origin=Origin.IR, message="x")


def test_an_issue_survives_a_json_round_trip() -> None:
    issue = E_TOY("broken", path="objects[0].size", objects=["title"])
    assert Issue.model_validate_json(issue.model_dump_json()) == issue


def test_a_code_is_defined_once() -> None:
    codes = make_issue_code_registry()
    codes.register(E_TOY)
    codes.register(E_TOY)  # the same definition again is harmless
    with pytest.raises(DuplicatePluginError, match="'E-TOY'"):
        codes.register(IssueCode("E-TOY", Origin.IR, "a second meaning for the same code"))


def test_the_core_defines_its_own_code() -> None:
    assert "E-ALLOW" in ISSUE_CODES
