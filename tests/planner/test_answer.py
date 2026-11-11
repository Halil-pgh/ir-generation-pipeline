"""Reading the planner's answer: its JSON, its draft files, and what no schema checks."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from irpipe.planner import PlannerSettings, Wishes
from irpipe.planner.answer import (
    Draft,
    briefs_in,
    extract,
    plan_problems,
    read_draft,
    write_draft,
)
from irpipe.schema.brief import FrameBrief, LessonPlan
from irpipe.schema.request import PlannerRequest

SETTINGS = PlannerSettings()


def draft(tmp_path: Path, text: str, kept: dict[str, Path] | None = None, **wish: Any) -> Draft:
    data, problems = extract(text)
    assert data is not None and not problems, problems
    made, problems = write_draft(data, tmp_path / "draft", kept or {}, Wishes(**wish))
    assert not problems
    return made


def read(made: Draft) -> tuple[LessonPlan, dict[str, FrameBrief]]:
    lesson, briefs, problems = read_draft(made)
    assert lesson is not None and not problems, problems
    return lesson, briefs


def test_the_json_is_found_in_a_fence_or_between_the_outer_braces(kit: Any) -> None:
    whole = {"lesson_plan": kit.LESSON, "briefs": [kit.BRIEF]}
    assert extract(kit.ONE)[0] is not None
    assert extract("Sure: " + json.dumps(whole) + " That is all.") == (whole, [])
    assert extract("No JSON here.") == (
        None, ['the answer holds no JSON object: answer with {"lesson_plan": ...}'],
    )  # fmt: skip
    data, problems = extract('```json\n{"lesson_plan": {}, "briefs": [}\n```')
    assert data is None and problems[0].startswith("the answer is not valid JSON: ")
    assert "Expecting value (line 1, column 32 of the object)" in problems[0]


@pytest.mark.parametrize(
    ("body", "said"),
    [
        ('{"lesson_plan": {}}', ["the answer has no 'briefs'"]),
        ('{"lesson_plan": {}, "briefs": [], "notes": 1}',
         ["the answer holds 'notes'; it holds only lesson_plan and briefs"]),
        ('{"lesson_plan": [], "briefs": [1]}',
         ["lesson_plan is a JSON object", "briefs is a list of JSON objects, one brief each"]),
        ("```json\n[1, 2]\n```",
         ["the answer is JSON, but not an object with lesson_plan and briefs"]),
    ],
)  # fmt: skip
def test_an_answer_of_the_wrong_shape_is_told_what_it_holds(body: str, said: list[str]) -> None:
    assert extract(body) == (None, said)


def test_the_draft_is_read_as_the_orchestrator_reads_it(kit: Any, tmp_path: Path) -> None:
    made = draft(tmp_path, kit.THREE)
    assert made.answered == ("two_vectors", "projection", "recap")
    assert sorted(p.name for p in (tmp_path / "draft").iterdir()) == [
        "lesson_plan.json", "projection.brief.json", "recap.brief.json", "two_vectors.brief.json",
    ]  # fmt: skip
    lesson, briefs = read(made)
    assert [f.id for f in lesson.frames] == list(briefs)
    assert plan_problems(lesson, briefs, made, settings=SETTINGS, wishes=Wishes()) == []


def test_the_problems_of_every_file_come_back_each_said_once(kit: Any, tmp_path: Path) -> None:
    plan = kit.lesson(("projection", "define"), ("recap", "summary"), goals=[])
    bad = kit.brief("recap", "summary", focus=["nothing"])
    made = draft(tmp_path, kit.answer(plan, [kit.brief(), bad, kit.brief("extra")]))
    lesson, briefs, problems = read_draft(made)
    assert lesson is None and briefs == {}
    assert sum("lesson_plan.json" in p for p in problems) == 1  # not once a brief
    assert any("goals" in p for p in problems)
    assert any("focus names 'nothing'" in p for p in problems)


def test_a_brief_twice_and_a_brief_without_a_good_id_are_caught(kit: Any, tmp_path: Path) -> None:
    data, _ = extract(kit.answer(kit.lesson(("projection", "define")), [kit.brief()] * 2))
    assert data is not None
    _, problems = write_draft(data, tmp_path, {}, Wishes())
    assert problems == ["two briefs have the id 'projection': one brief per frame"]
    data, _ = extract(kit.answer(kit.lesson(("projection", "define")), [kit.brief(id=None)]))
    assert data is not None
    made, problems = write_draft(data, tmp_path / "2", {}, Wishes())
    assert problems == [
        "briefs[0] has the id null: a brief's id is its frame's id, a letter, then letters, "
        "digits or _"
    ]
    assert made.answered == ()


def test_every_frame_needs_a_brief_with_its_purpose_and_the_count_is_kept(
    kit: Any, tmp_path: Path
) -> None:
    plan = kit.lesson(("projection", "define"), ("recap", "summary"))
    made = draft(tmp_path, kit.answer(plan, [kit.brief("projection", "example")]))
    lesson, briefs = read(made)
    settings = PlannerSettings(max_frames=1)
    assert plan_problems(lesson, briefs, made, settings=settings, wishes=Wishes(frames=3)) == [
        "brief 'projection' has the purpose 'example', but the lesson plan gives frame "
        "'projection' the purpose 'define': make them the same",
        "frame 'recap' of the lesson plan has no brief",
        "the lesson has 2 frames; it may have at most 1",
        "the user asks for exactly 3 frames; the lesson has 2",
    ]


def test_the_wishes_win_over_the_lesson_and_over_a_brief_that_would_undo_them(
    kit: Any, tmp_path: Path
) -> None:
    changes = {"aspect": "4:3", "typography": {"scale": "large", "lang": "en"}}
    plan = kit.lesson(("projection", "define"))
    made = draft(
        tmp_path, kit.answer(plan, [kit.brief(render_profile=changes)]), aspect="9:16", lang="tr"
    )
    lesson, _ = read(made)
    assert (lesson.style.render_profile.aspect, lesson.style.render_profile.typography.lang) == (
        "9:16", "tr",
    )  # fmt: skip
    written = json.loads((tmp_path / "draft" / "projection.brief.json").read_text())
    assert written["render_profile"] == {
        "aspect": "9:16", "typography": {"scale": "large", "lang": "tr"},
    }  # fmt: skip
    assert "platform" not in written["render_profile"]  # what the model left out stays out
    assert Wishes(frames=2, platform="tiktok").describe() == (
        "The user asks for exactly 2 frames; the platform tiktok."
    )
    assert Wishes().describe() == ""


@pytest.mark.parametrize(
    ("wish", "said"),
    [
        ({"platform": "tiktk"}, "did you mean 'tiktok'?"),
        ({"aspect": "30:1"}, "outside the supported range"),
        ({"lang": "Turkish"}, "String should match pattern"),
        ({"frames": 0}, "greater than or equal to 1"),
    ],
)
def test_a_wish_the_project_cannot_meet_fails_at_once(wish: dict[str, Any], said: str) -> None:
    with pytest.raises(ValidationError, match=said):
        Wishes(**wish)


def revision(
    kit: Any, tmp_path: Path, kind: str, frames: list[tuple[str, str]], briefs: list[str]
) -> list[str]:
    """The revision problems of an answer with ``frames`` and the briefs ``briefs`` (ids),
    for a ``kind`` request on frame "projection" of the three-frame lesson."""
    purposes = dict(frames)
    plan = kit.lesson(*frames)
    written = [kit.brief(b, purposes.get(b, "define")) for b in briefs]
    before = LessonPlan.model_validate(
        kit.lesson(("two_vectors", "introduce"), ("projection", "define"), ("recap", "summary"))
    )
    earlier = draft(tmp_path / "before", kit.THREE)
    made = draft(tmp_path, kit.answer(plan, written), kept=earlier.briefs)
    lesson, all_briefs = read(made)
    request = PlannerRequest(frame="projection", kind=kind, reason="too much")
    return plan_problems(
        lesson, all_briefs, made, settings=SETTINGS, wishes=Wishes(),
        request=request, before=before,
    )  # fmt: skip


THREE = [("two_vectors", "introduce"), ("projection", "define"), ("recap", "summary")]
SPLIT = [("two_vectors", "introduce"), ("shadow", "define"), ("formula", "define"),
         ("recap", "summary")]  # fmt: skip


def test_a_revision_must_do_what_was_asked(kit: Any, tmp_path: Path) -> None:
    def problems(kind: str, frames: list[tuple[str, str]], briefs: list[str]) -> list[str]:
        return revision(kit, tmp_path / kind / str(len(frames)) / "_".join(briefs), kind,
                        frames, briefs)  # fmt: skip

    assert problems("shorten", THREE, ["projection"]) == []
    assert problems("shorten", THREE, ["recap"]) == [
        "the answer holds no brief for frame 'projection': write its new brief"
    ]
    assert problems("shorten", [THREE[0], THREE[1]], ["projection"]) == [
        "keep the lesson's frames as they are (two_vectors, projection, recap): only the brief "
        "of 'projection' changes"
    ]
    assert problems("split", SPLIT, ["shadow", "formula"]) == []
    assert problems("split", SPLIT, ["shadow"]) == [
        "frame 'formula' of the lesson plan has no brief"
    ]
    assert problems("split", THREE, ["projection"]) == [
        "frame 'projection' is split: the lesson plan no longer lists it, but the two frames "
        "that take its place, under new ids"
    ]
    moved = [SPLIT[1], SPLIT[0], SPLIT[2], SPLIT[3]]
    assert problems("split", moved, ["shadow", "formula"]) == [
        "put two new frames (new ids) where 'projection' was, the others as they were: "
        "two_vectors, <new frame>, <new frame>, recap"
    ]
    assert problems("fix", [THREE[1]], ["projection"]) == []
    assert problems("fix", [THREE[0], THREE[2]], []) == [
        "keep frame 'projection' under its id: change its brief, do not replace it"
    ]


def test_the_briefs_of_a_folder_are_found_by_their_name(tmp_path: Path) -> None:
    for name in ("b.brief.json", "a.brief.json", "lesson_plan.json", "notes.json"):
        (tmp_path / name).write_text("{}")
    assert list(briefs_in(tmp_path)) == ["a", "b"]
