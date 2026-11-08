"""allow entries: which issues an entry accepts, and which entries are malformed.

The example picture is a vector projection: vectors ``a`` and ``b``, and a
dashed projection line ``proj`` that runs through ``b``'s label on purpose.
"""

import pytest

from irpipe.core import (
    Allow,
    IssueCode,
    Origin,
    apply_allows,
    check_allows,
    make_issue_code_registry,
)

CODES = make_issue_code_registry()
W_OVERLAP = CODES.register(IssueCode("W-OVERLAP", Origin.IR, "two objects overlap", allowable=True))
W_EMPTY_SIDE = CODES.register(
    IssueCode("W-EMPTY-SIDE", Origin.IR, "one side of the picture is empty", allowable=True)
)
E_SUBTITLE = CODES.register(IssueCode("E-SUBTITLE", Origin.IR, "something is in the band"))

REASON = "the projection line runs through b's label to show where it lands"


def accepted(allow: Allow, *objects: str) -> bool:
    """Does ``allow`` accept a W-OVERLAP issue about ``objects``?"""
    (issue,) = apply_allows([W_OVERLAP("overlap", objects=objects)], [allow], codes=CODES)
    return issue.allowed_because == allow.reason


# Matching


def test_an_entry_accepts_an_issue_about_the_objects_it_names() -> None:
    assert accepted(Allow(code="W-OVERLAP", objects=("proj",), reason=REASON), "proj", "b")


def test_an_id_also_covers_its_parts() -> None:
    allow = Allow(code="W-OVERLAP", objects=("b",), reason=REASON)
    assert accepted(allow, "proj", "b.label")
    assert not accepted(allow, "proj", "bx.label")  # a prefix of the name is not enough


def test_every_named_object_must_be_involved() -> None:
    allow = Allow(code="W-OVERLAP", objects=("proj", "b.label"), reason=REASON)
    assert accepted(allow, "proj", "b.label")
    assert not accepted(allow, "proj", "a.label")


def test_an_entry_without_objects_does_not_accept_every_issue_of_its_code() -> None:
    blanket = Allow(code="W-OVERLAP", reason=REASON)
    assert not accepted(blanket, "proj", "b.label")
    (issue,) = apply_allows(
        [W_EMPTY_SIDE("the right side is empty")],
        [Allow(code="W-EMPTY-SIDE", reason="the empty right side is kept for the caption")],
        codes=CODES,
    )
    assert not issue.is_open


def test_an_entry_only_accepts_its_own_code() -> None:
    assert not accepted(Allow(code="W-EMPTY-SIDE", objects=("proj",), reason=REASON), "proj")


def test_a_code_that_is_not_allowable_stays_open_whatever_the_entries_say() -> None:
    (issue,) = apply_allows(
        [E_SUBTITLE("the title is in the band", objects=["title"])],
        [Allow(code="E-SUBTITLE", objects=("title",), reason=REASON)],
        codes=CODES,
    )
    assert issue.is_open


def test_the_ir_layer_can_widen_what_an_id_covers() -> None:
    members = {"vectors": {"a", "b"}}

    def covers_groups(named: str, reported: str) -> bool:
        return reported == named or reported in members.get(named, set())

    (issue,) = apply_allows(
        [W_OVERLAP("overlap", objects=["b", "proj"])],
        [Allow(code="W-OVERLAP", objects=("vectors",), reason=REASON)],
        codes=CODES,
        covers=covers_groups,
    )
    assert issue.allowed_because == REASON


# Malformed entries


def messages(allows: list[Allow], known_ids: set[str] | None = None) -> list[str]:
    return [i.message for i in check_allows(allows, known_ids=known_ids, codes=CODES)]


def test_a_well_formed_entry_passes() -> None:
    allow = Allow(code="W-OVERLAP", objects=("proj", "b.label"), reason=REASON)
    assert messages([allow], known_ids={"proj", "b"}) == []


def test_an_unknown_code_gets_a_suggestion() -> None:
    (issue,) = check_allows([Allow(code="W-OVERLPA", reason=REASON)], codes=CODES)
    assert issue.code == "E-ALLOW"
    assert issue.path == "allow[0].code"
    assert issue.hint is not None
    assert issue.hint.startswith("did you mean W-OVERLAP?")
    assert "W-EMPTY-SIDE" in issue.hint


def test_a_code_that_must_be_fixed_cannot_be_allowed() -> None:
    assert messages([Allow(code="E-SUBTITLE", reason=REASON)]) == [
        "E-SUBTITLE cannot be allowed; it always has to be fixed"
    ]


@pytest.mark.parametrize("reason", ["", "ok", "this is intended"])
def test_the_reason_must_explain(reason: str) -> None:
    (issue,) = check_allows([Allow(code="W-EMPTY-SIDE", reason=reason)], codes=CODES)
    assert issue.path == "allow[0].reason"


def test_named_objects_must_exist_when_the_ids_are_known() -> None:
    allow = Allow(code="W-OVERLAP", objects=("proj", "ghost.label"), reason=REASON)
    (issue,) = check_allows([allow], known_ids={"proj"}, codes=CODES)
    assert issue.message == "allow[0] names unknown object 'ghost.label'"
    assert issue.path == "allow[0].objects[1]"
