"""What the planner hands on: the lesson plan and one brief per frame (analysis §1).

    lesson = LessonPlan.model_validate_json(lesson_text)    # lesson_plan.json
    brief = FrameBrief.model_validate_json(brief_text)       # brief.json, one frame
    style = frame_style(brief, lesson)                       # what the frame is drawn with

The **lesson plan** holds what stays the same through a lesson: its goals,
the misconceptions to meet, the frames in the order they are told, and a
style sheet: concept -> color, notation, and the render profile (canvas,
subtitles, type, theme). A **frame brief** says what one picture must do
in words a program can check: its purpose, the intent and focus, the
``must_show`` items with ids, the exact texts, constraints split into
``must`` and ``should``, and a free description of the picture.

A frame inherits the lesson's style and may override any part of it: its
concept colors and notation entries win over the lesson's, and any field
of the render profile it writes wins over the lesson's, the rest coming
from the lesson. Later, the orchestrator lays a project's settings and the
user's explicit wishes over the planner's choice in the same way, in this
order of precedence: the user's request, then the project, then the
planner (``overlay``).

The orchestrator (step 19) writes the IR's locked header from the frame's
style and brief: ``intent`` -> intent, concept colors -> colors, the render
profile -> frame, typography and theme.
"""

from collections import Counter
from typing import Annotated, Any, Final, Literal, Self

from pydantic import AfterValidator, BaseModel, Field, model_validator

from irpipe.schema.base import StrictModel
from irpipe.schema.color import Color, ColorName
from irpipe.schema.ir.common import Name
from irpipe.schema.render_profile import (
    Insets,
    RenderProfile,
    Subtitle,
    Theme,
    Typography,
    check_aspect,
)

BRIEF_VERSION: Final = "frame-brief/1.0"
LESSON_VERSION: Final = "lesson-plan/1.0"

Purpose = Literal["introduce", "define", "example", "counterexample", "summary"]
"""What a frame does for the lesson: brings an idea in, defines it, shows an
example of it, shows what it is not, or sums up."""

Text = Annotated[str, Field(min_length=1)]


class MustShow(StrictModel):
    """Something the picture must show, with an id the IR can name (``"covers": ["m1"]``)."""

    id: Name
    text: Text
    """What it is, in plain words: "the projection of a onto b, as an arrow"."""
    data: dict[str, Any] | None = None
    """Exact values it shows, when it has some: ``{"a": [3, 2], "b": [4, 0]}``."""


class Texts(StrictModel):
    """Words that appear in the picture exactly as written, in the frame's language."""

    title: Text | None = None
    labels: dict[Name, Text] = Field(default_factory=dict)
    """Label name -> its words: ``{"a": "a", "proj": "proj_b a"}``."""
    subtitle: Text | None = None
    """What the subtitle band says, when the frame burns one in."""


class Constraints(StrictModel):
    """What the picture must do, and what it should do if it can."""

    must: tuple[Text, ...] = ()
    should: tuple[Text, ...] = ()


class ProfileChanges(StrictModel):
    """The parts of the render profile a frame (or a project, or the user) changes.

    Every field is optional: what is not written comes from the layer below.
    Nested parts change field by field too: ``{"subtitle": {"mode": "burn_in"}}``
    keeps the number of lines the lesson chose.
    """

    aspect: Annotated[str, AfterValidator(check_aspect)] | None = None
    resolution: int | None = Field(default=None, ge=360, le=4320)
    platform: str | None = None
    margins: Insets | None = None
    subtitle: Subtitle | None = None
    typography: Typography | None = None
    theme: Theme | None = None


class Style(StrictModel):
    """What a lesson's frames are drawn with: concept colors, notation and the render profile."""

    concept_colors: dict[ColorName, Color] = Field(default_factory=dict)
    """Concept -> color: one concept keeps one color through the lesson."""
    notation: dict[Name, Text] = Field(default_factory=dict)
    """Concept -> how it is written, in TeX: ``{"projection": "\\\\operatorname{proj}_b a"}``."""
    render_profile: RenderProfile


class FrameOutline(StrictModel):
    """A frame in the lesson's order: its id, purpose and a line of what it shows."""

    id: Name
    purpose: Purpose
    summary: Text


class LessonPlan(StrictModel):
    """lesson_plan.json: the lesson as a whole."""

    version: Literal["lesson-plan/1.0"] = LESSON_VERSION
    id: Name
    topic: Text
    """The topic as the user asked for it."""
    goals: tuple[Text, ...] = Field(min_length=1)
    misconceptions: tuple[Text, ...] = ()
    """What learners often get wrong, for the frames to meet."""
    frames: tuple[FrameOutline, ...] = Field(min_length=1)
    """The frames in the order they are told."""
    style: Style

    @model_validator(mode="after")
    def _frame_ids_unique(self) -> Self:
        _unique([frame.id for frame in self.frames], "frame")
        return self

    def frame(self, frame_id: str) -> FrameOutline:
        for outline in self.frames:
            if outline.id == frame_id:
                return outline
        raise ValueError(f"lesson '{self.id}' has no frame '{frame_id}'")


class FrameBrief(StrictModel):
    """brief.json: what one picture must do."""

    version: Literal["frame-brief/1.0"] = BRIEF_VERSION
    id: Name
    """The frame's id, as the lesson plan lists it."""
    lesson: Name | None = None
    """The lesson it belongs to; a frame on its own gives its whole render profile."""
    purpose: Purpose
    intent: Text
    """What the viewer should understand; it becomes the IR's intent."""
    focus: tuple[Name, ...] = ()
    """The ``must_show`` items the eye should go to first."""
    must_show: tuple[MustShow, ...] = Field(min_length=1)
    texts: Texts = Field(default_factory=Texts)
    concept_colors: dict[ColorName, Color] = Field(default_factory=dict)
    notation: dict[Name, Text] = Field(default_factory=dict)
    constraints: Constraints = Field(default_factory=Constraints)
    render_profile: ProfileChanges = Field(default_factory=ProfileChanges)
    composition_notes: Text | None = None
    """The picture described in words: what goes where, what stands out."""

    @model_validator(mode="after")
    def _ids_unique_and_focus_known(self) -> Self:
        ids = [item.id for item in self.must_show]
        _unique(ids, "must_show")
        unknown = [name for name in self.focus if name not in ids]
        if unknown:
            raise ValueError(
                f"focus names {', '.join(repr(n) for n in unknown)}, which "
                f"{'is' if len(unknown) == 1 else 'are'} not in must_show "
                f"(its ids: {', '.join(ids)})"
            )
        return self


def frame_style(brief: FrameBrief, lesson: LessonPlan | None = None) -> Style:
    """The style ``brief`` is drawn with: the lesson's, with the frame's own changes over it.

    Raises ValueError when the brief does not belong to the lesson, or when,
    without a lesson, the brief does not give an aspect.
    """
    if lesson is None:
        if brief.render_profile.aspect is None:
            raise ValueError(
                f"brief '{brief.id}' has no lesson, so its render_profile must give an aspect"
            )
        profile = overlay(None, brief.render_profile)
        return Style(
            concept_colors=brief.concept_colors, notation=brief.notation, render_profile=profile
        )
    if brief.lesson != lesson.id:
        raise ValueError(
            f"brief '{brief.id}' belongs to lesson '{brief.lesson}', not '{lesson.id}'"
        )
    lesson.frame(brief.id)
    style = lesson.style
    return Style(
        concept_colors={**style.concept_colors, **brief.concept_colors},
        notation={**style.notation, **brief.notation},
        render_profile=overlay(style.render_profile, brief.render_profile),
    )


def overlay(base: RenderProfile | None, *changes: ProfileChanges) -> RenderProfile:
    """``base`` with each layer of ``changes`` laid over it in turn; the last one wins.

    Only what a layer writes counts, field by field, nested parts included:
    the planner's profile, then the project's changes, then the user's.
    """
    merged: dict[str, Any] = base.model_dump(exclude_unset=False) if base is not None else {}
    for layer in changes:
        merged = _laid_over(merged, layer)
    return RenderProfile.model_validate(merged)


def _laid_over(below: dict[str, Any], layer: BaseModel) -> dict[str, Any]:
    result = dict(below)
    for name in layer.model_fields_set:
        value = getattr(layer, name)
        if value is None:  # an empty field leaves the layer below as it is
            continue
        under = result.get(name)
        if isinstance(value, BaseModel):  # a nested part changes field by field, when it can
            result[name] = (
                _laid_over(under, value) if isinstance(under, dict) else value.model_dump()
            )
        else:
            result[name] = value
    return result


def _unique(ids: list[str], what: str) -> None:
    twice = [name for name, count in Counter(ids).items() if count > 1]
    if twice:
        names = ", ".join(repr(name) for name in twice)
        verb = "is" if len(twice) == 1 else "are"
        raise ValueError(f"{what} ids must be unique; {names} {verb} used more than once")
