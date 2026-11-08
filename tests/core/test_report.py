"""READY: no open errors, every warning fixed or allowed, and every stage ran."""

import pytest
from pydantic import ValidationError

from irpipe.core import Allow, IssueCode, Origin, Report, Status, make_issue_code_registry

CODES = make_issue_code_registry()
E_OFFSCREEN = CODES.register(IssueCode("E-OFFSCREEN", Origin.IR, "cut off by the frame edge"))
W_SAFE_AREA = CODES.register(
    IssueCode("W-SAFE-AREA", Origin.IR, "outside the safe area", allowable=True)
)

REASON = "the arrow tip leaves the safe area on purpose"


def test_no_issues_is_ready() -> None:
    report = Report.build([], codes=CODES)
    assert report.status is Status.READY
    assert report.ready
    assert report.headline == "READY"


def test_an_open_warning_is_not_ready() -> None:
    report = Report.build([W_SAFE_AREA("arrow leaves", objects=["arrow"])], codes=CODES)
    assert report.status is Status.NOT_READY
    assert (report.errors, report.warnings, report.allowed) == (0, 1, 0)
    assert report.headline == "NOT READY (0 errors, 1 warning)"


def test_an_allowed_warning_is_ready_and_stays_in_the_report() -> None:
    report = Report.build(
        [W_SAFE_AREA("arrow leaves", objects=["arrow"])],
        allows=[Allow(code="W-SAFE-AREA", objects=("arrow",), reason=REASON)],
        codes=CODES,
    )
    assert report.ready
    assert report.allowed == 1
    (issue,) = report.issues
    assert issue.allowed_because == REASON


def test_an_error_that_cannot_be_allowed_keeps_it_from_being_ready() -> None:
    report = Report.build(
        [E_OFFSCREEN("title is cut off", objects=["title"]), W_SAFE_AREA("x", objects=["x"])],
        allows=[
            Allow(code="E-OFFSCREEN", objects=("title",), reason=REASON),
            Allow(code="W-SAFE-AREA", objects=("x",), reason=REASON),
        ],
        codes=CODES,
    )
    assert report.status is Status.NOT_READY
    assert (report.errors, report.warnings, report.allowed) == (1, 0, 1)


def test_a_stopped_run_is_never_ready() -> None:
    report = Report.build([E_OFFSCREEN("x", objects=["x"])], stopped_at="validate", codes=CODES)
    assert report.status is Status.STOPPED
    assert report.headline == "STOPPED at 'validate' (1 error, 0 warnings)"


def test_a_report_survives_report_json() -> None:
    report = Report.build(
        [W_SAFE_AREA("arrow leaves", objects=["arrow"]), E_OFFSCREEN("cut", objects=["t"])],
        allows=[Allow(code="W-SAFE-AREA", objects=("arrow",), reason=REASON)],
        codes=CODES,
    )
    assert Report.model_validate_json(report.model_dump_json()) == report


def test_a_report_whose_counts_disagree_with_its_issues_is_refused() -> None:
    issue = E_OFFSCREEN("cut", objects=["t"])
    with pytest.raises(ValidationError, match="do not match the issues"):
        Report(status=Status.READY, errors=0, warnings=0, allowed=0, issues=(issue,))
