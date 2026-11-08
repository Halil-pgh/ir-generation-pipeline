"""The verdict of one run: is the picture READY, and if not, why not.

    report = Report.build(result.issues, allows=ir.allow, stopped_at=result.stopped_at)
    report.headline   # "NOT READY (1 error, 2 warnings)"

A picture is READY when the run went through every stage and no issue is
left open: no errors, and every warning fixed or accepted with an ``allow``
entry (core/allow.py). A visual critic's approval joins this condition later
(analysis §1). The orchestrator writes the report as report.json.
"""

from collections.abc import Iterable, Sequence
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from irpipe.core.allow import Allow, Covers, apply_allows, covers_by_name
from irpipe.core.issues import ISSUE_CODES, Issue, IssueCode, Severity
from irpipe.core.registry import Registry


class Status(StrEnum):
    READY = "READY"
    NOT_READY = "NOT_READY"  # every stage ran; open issues remain
    STOPPED = "STOPPED"  # a stage could not produce its output, so later stages did not run


class Report(BaseModel):
    """Status, open-issue counts and every issue of one run (allowed ones included)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Status
    stopped_at: str | None = None
    errors: int  # open errors
    warnings: int  # open warnings
    allowed: int  # issues an allow entry accepted
    issues: tuple[Issue, ...] = ()

    @classmethod
    def build(
        cls,
        issues: Iterable[Issue],
        *,
        allows: Sequence[Allow] = (),
        stopped_at: str | None = None,
        codes: Registry[IssueCode] = ISSUE_CODES,
        covers: Covers = covers_by_name,
    ) -> Self:
        """Apply the allow entries to the issues and count what is left open."""
        marked = apply_allows(issues, allows, codes=codes, covers=covers)
        status, errors, warnings, allowed = _tally(marked, stopped_at)
        return cls(
            status=status,
            stopped_at=stopped_at,
            errors=errors,
            warnings=warnings,
            allowed=allowed,
            issues=marked,
        )

    @model_validator(mode="after")
    def _counts_match_issues(self) -> Self:
        # A report read back from report.json must agree with its own issue list.
        if (self.status, self.errors, self.warnings, self.allowed) != _tally(
            self.issues, self.stopped_at
        ):
            raise ValueError("status and counts do not match the issues; use Report.build()")
        return self

    @property
    def ready(self) -> bool:
        return self.status is Status.READY

    @property
    def headline(self) -> str:
        """One line for people and for the agent: READY, NOT READY (...) or STOPPED at ..."""
        counts = f"{_plural(self.errors, 'error')}, {_plural(self.warnings, 'warning')}"
        if self.status is Status.STOPPED:
            return f"STOPPED at '{self.stopped_at}' ({counts})"
        if self.status is Status.NOT_READY:
            return f"NOT READY ({counts})"
        return "READY"


def _tally(issues: Sequence[Issue], stopped_at: str | None) -> tuple[Status, int, int, int]:
    errors = sum(1 for i in issues if i.is_open and i.severity is Severity.ERROR)
    warnings = sum(1 for i in issues if i.is_open and i.severity is Severity.WARNING)
    allowed = sum(1 for i in issues if not i.is_open)
    if stopped_at is not None:
        status = Status.STOPPED
    elif errors or warnings:
        status = Status.NOT_READY
    else:
        status = Status.READY
    return status, errors, warnings, allowed


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"
