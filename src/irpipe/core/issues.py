"""Problems found in a picture, and the one registry that defines their codes.

A problem in a picture never raises. The stage that finds it reports an
``Issue``: a code such as ``E-SUBTITLE``, a message, and where to look (a JSON
path in the IR, object ids, a hint for the fix). Exceptions (core/errors.py)
are kept for a pipeline that is set up or written wrongly.

Every code is defined exactly once, as an ``IssueCode`` registered in
``ISSUE_CODES`` by the module whose stage or check reports it. Calling the
code builds an issue:

    E_REF = ISSUE_CODES.register(
        IssueCode("E-REF", Origin.IR, "a reference names an unknown object or anchor")
    )
    ...
    ctx.report(E_REF("'v.tipp' is not an anchor", path="objects[2].from", objects=["arrow"]))

The first letter of a code is its severity: ``E-`` is an error, ``W-`` a
warning. The origin says whose problem it is, which decides where the
orchestrator sends it (step 19, analysis §1):

    ir            the IR is wrong              -> the IR agent, in IR terms
    capability    the backend cannot draw it   -> lowered automatically, else the agent
    internal      a bug in our compiler        -> a person; the agent cannot fix it
    environment   a missing font, no LaTeX     -> a person
    infeasible    the brief does not fit       -> the planner
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from irpipe.core.registry import Registry

_CODE_FORMAT = re.compile(r"[EW](-[A-Z0-9]+)+")


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class Origin(StrEnum):
    """Where a problem comes from; see the module docstring for where each one goes."""

    IR = "ir"
    CAPABILITY = "capability"
    INTERNAL = "internal"
    ENVIRONMENT = "environment"
    INFEASIBLE = "infeasible"


def severity_of(code: str) -> Severity:
    """``E-...`` is an error, ``W-...`` a warning; anything else is not a valid code."""
    if not _CODE_FORMAT.fullmatch(code):
        raise ValueError(
            f"an issue code looks like E-NAME or W-NAME (capitals, digits, hyphens), got {code!r}"
        )
    return Severity.ERROR if code.startswith("E") else Severity.WARNING


class Issue(BaseModel):
    """One problem found in one run, as report.json lists it.

    Build issues by calling their ``IssueCode``, which fills in ``severity``
    and ``origin``. ``path`` is a JSON path into the IR (``objects[3].size``),
    ``objects`` the ids involved (``v`` or a part of it such as ``v.label``).
    The pipeline fills in ``stage``; ``allowed_because`` is set when an
    ``allow`` entry accepts the issue (core/allow.py).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    severity: Severity
    origin: Origin
    message: str
    path: str | None = None
    objects: tuple[str, ...] = ()
    hint: str | None = None
    stage: str | None = None
    allowed_because: str | None = None

    @model_validator(mode="after")
    def _severity_matches_code(self) -> Self:
        if self.severity is not severity_of(self.code):
            raise ValueError(f"{self.code} is an {severity_of(self.code)}, not a {self.severity}")
        return self

    @property
    def is_open(self) -> bool:
        """True while the issue still counts against READY (no allow entry accepted it)."""
        return self.allowed_because is None


@dataclass(frozen=True)
class IssueCode:
    """The definition of one kind of problem.

    ``summary`` is the one line the list of codes shows. ``allowable`` says
    whether an IR may accept the problem on purpose with an ``allow`` entry.
    Only warnings that originate in the IR can be allowable: an error always
    has to be fixed (READY means no errors), and the agent cannot accept a
    missing font or a compiler bug.
    """

    code: str
    origin: Origin
    summary: str
    allowable: bool = False

    def __post_init__(self) -> None:
        if severity_of(self.code) is Severity.ERROR and self.allowable:
            raise ValueError(
                f"{self.code}: an error always has to be fixed, so it cannot be allowable"
            )
        if self.allowable and self.origin is not Origin.IR:
            raise ValueError(
                f"{self.code}: only warnings that originate in the IR can be allowable, "
                f"this one originates in {self.origin}"
            )

    @property
    def severity(self) -> Severity:
        return severity_of(self.code)

    def __call__(
        self,
        message: str,
        *,
        path: str | None = None,
        objects: Iterable[str] = (),
        hint: str | None = None,
    ) -> Issue:
        """Build an issue of this kind."""
        return Issue(
            code=self.code,
            severity=self.severity,
            origin=self.origin,
            message=message,
            path=path,
            objects=tuple(objects),
            hint=hint,
        )


def make_issue_code_registry() -> Registry[IssueCode]:
    """A fresh, empty code registry. Tests use one so their toy codes stay out of ISSUE_CODES."""
    return Registry("issue code", key=lambda definition: definition.code)


ISSUE_CODES = make_issue_code_registry()
"""Every issue code of the pipeline. Defining a code twice raises DuplicatePluginError."""
