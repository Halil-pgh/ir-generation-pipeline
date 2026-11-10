"""The planner's output, lesson_plan.json and brief.json, and a frame's inherited style."""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from irpipe.schema.brief import FrameBrief, LessonPlan, ProfileChanges, frame_style, overlay
from irpipe.schema.render_profile import ModularScale, RenderProfile

ROOT = Path(__file__).parent.parent.parent
EXAMPLE = ROOT / "examples" / "projection"
SPEC = ROOT / "docs" / "spec"


def load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((EXAMPLE / name).read_text(encoding="utf-8"))
    return data


def lesson(**changes: Any) -> LessonPlan:
    return LessonPlan.model_validate({**load("lesson_plan.json"), **changes})


def brief(**changes: Any) -> FrameBrief:
    return FrameBrief.model_validate({**load("brief.json"), **changes})


# The examples


@pytest.mark.parametrize(
    ("name", "stem"), [("lesson_plan.json", "lesson_plan"), ("brief.json", "brief")]
)
def test_the_examples_pass_their_model_and_their_published_schema(name: str, stem: str) -> None:
    model = LessonPlan if stem == "lesson_plan" else FrameBrief
    model.model_validate_json((EXAMPLE / name).read_text(encoding="utf-8"))
    schema = json.loads((SPEC / f"{stem}.schema.json").read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(load(name))) == []


def test_the_example_brief_is_the_brief_of_the_example_picture() -> None:
    ir = load("ir.json")
    style = frame_style(brief(), lesson())
    assert brief().intent == ir["intent"]
    assert json.loads(json.dumps(style.concept_colors)) == ir["colors"]
    assert style.render_profile.aspect == ir["frame"]["aspect"]
    assert style.render_profile.typography.lang == ir["typography"]["lang"]
    assert lesson().frame("projection").purpose == brief().purpose


# What a brief must hold


def test_must_show_ids_are_unique() -> None:
    items = [{"id": "m1", "text": "one"}, {"id": "m1", "text": "two"}]
    with pytest.raises(ValidationError, match="must_show ids must be unique; 'm1' is used more"):
        brief(must_show=items, focus=[])


def test_focus_names_must_show_items() -> None:
    with pytest.raises(ValidationError, match="focus names 'shadw', which is not in must_show"):
        brief(focus=["shadw"])


def test_a_brief_shows_at_least_one_thing_and_has_a_known_purpose() -> None:
    with pytest.raises(ValidationError, match="must_show"):
        brief(must_show=[], focus=[])
    with pytest.raises(ValidationError, match="purpose"):
        brief(purpose="decorate")


def test_unknown_fields_are_refused() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        brief(colour="red")


def test_a_lessons_frame_ids_are_unique() -> None:
    frames = [{"id": "f", "purpose": "introduce", "summary": "x"}] * 2
    with pytest.raises(ValidationError, match="frame ids must be unique; 'f' is used"):
        lesson(frames=frames)


# A frame's style


def test_a_frame_inherits_the_lessons_style_and_overrides_parts_of_it() -> None:
    changes = {
        "concept_colors": {"proj": "#FC6255"},
        "notation": {"dot": "\\langle a, b \\rangle"},
        "render_profile": {"subtitle": {"mode": "burn_in"}, "typography": {"lang": "tr"}},
    }
    style = frame_style(brief(**changes), lesson())
    assert style.concept_colors == {"a": "#FFD43B", "b": (88, 196, 221), "proj": "#FC6255"}
    assert style.notation["dot"] == "\\langle a, b \\rangle"
    assert style.notation["projection"] == "\\operatorname{proj}_b a"
    profile = style.render_profile
    assert (profile.subtitle.mode, profile.subtitle.lines) == ("burn_in", 2)  # lines: the lesson's
    assert (profile.typography.lang, profile.typography.scale) == ("tr", "comfortable")
    assert profile.aspect == "16:9"


def test_a_part_of_another_kind_replaces_the_lessons_whole() -> None:
    scale = {"render_profile": {"typography": {"scale": {"base": 40, "ratio": 1.25}}}}
    profile = frame_style(brief(**scale), lesson()).render_profile
    assert profile.typography.scale == ModularScale(base=40, ratio=1.25)


def test_a_brief_belongs_to_the_lesson_it_names() -> None:
    with pytest.raises(ValueError, match="belongs to lesson 'other', not 'vector_projection'"):
        frame_style(brief(lesson="other"), lesson())
    with pytest.raises(ValueError, match="lesson 'vector_projection' has no frame 'extra'"):
        frame_style(brief(id="extra"), lesson())


def test_a_brief_on_its_own_gives_its_whole_profile() -> None:
    with pytest.raises(ValueError, match="must give an aspect"):
        frame_style(brief(lesson=None))
    style = frame_style(brief(lesson=None, render_profile={"aspect": "9:16", "platform": "tiktok"}))
    assert (style.render_profile.aspect, style.render_profile.platform) == ("9:16", "tiktok")
    assert style.render_profile.resolution == 1080  # the profile's own default


def test_later_layers_win_the_user_over_the_project_over_the_planner() -> None:
    planner = RenderProfile(aspect="16:9", platform="plain")
    project = ProfileChanges.model_validate(
        {"platform": "youtube_shorts", "aspect": "9:16", "resolution": 2160}
    )
    user = ProfileChanges.model_validate({"aspect": "9:16", "platform": "tiktok"})
    profile = overlay(planner, project, user)
    assert (profile.aspect, profile.platform, profile.resolution) == ("9:16", "tiktok", 2160)
