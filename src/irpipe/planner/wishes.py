"""What the user asked for explicitly: the frame count, aspect, platform and language.

    wishes = Wishes(frames=3, aspect="9:16", platform="tiktok", lang="tr")
    wishes.describe()                   # told to the planner, in its first message
    lesson = wishes.lay_over_lesson(raw_lesson)
    brief = wishes.lay_over_brief(raw_brief)

The user's wish wins over the planner's choice (brief.py's order of
precedence: the user, then the project, then the planner). The planner is
told the wishes, and they are also laid over its answer before the answer
is checked: over the lesson's render profile, and over any part of a
brief's profile changes that would undo them (a frame that sets its own
aspect gets the user's). The layer is laid over the JSON the model wrote,
so what the model left out stays left out.
"""

from typing import Any, Self

from pydantic import Field, model_validator

from irpipe.platforms import PLATFORMS
from irpipe.schema.base import StrictModel
from irpipe.schema.brief import ProfileChanges


class Wishes(StrictModel):
    frames: int | None = Field(default=None, ge=1, le=20)
    """Exactly this many frames, when given."""
    aspect: str | None = None
    platform: str | None = None
    lang: str | None = None
    """The language of every text in the pictures (typography.lang), such as "tr"."""

    @model_validator(mode="after")
    def _known(self) -> Self:
        ProfileChanges.model_validate(self.changes())  # the aspect and the language
        if self.platform is not None and self.platform not in PLATFORMS:
            close = PLATFORMS.closest(self.platform)
            mean = f"did you mean '{close}'? " if close else ""
            raise ValueError(
                f"unknown platform '{self.platform}'; {mean}(the platforms: "
                f"{', '.join(PLATFORMS.names())})"
            )
        return self

    def changes(self) -> dict[str, Any]:
        """The wishes as render-profile changes, in the JSON's own form."""
        changes: dict[str, Any] = {}
        if self.aspect is not None:
            changes["aspect"] = self.aspect
        if self.platform is not None:
            changes["platform"] = self.platform
        if self.lang is not None:
            changes["typography"] = {"lang": self.lang}
        return changes

    def describe(self) -> str:
        """The wishes in words for the planner; "" when there are none."""
        said = []
        if self.frames is not None:
            said.append(f"exactly {self.frames} frame{'' if self.frames == 1 else 's'}")
        if self.aspect is not None:
            said.append(f"the aspect {self.aspect}")
        if self.platform is not None:
            said.append(f"the platform {self.platform}")
        if self.lang is not None:
            said.append(f"every text of the pictures in the language {self.lang!r}")
        return "The user asks for " + "; ".join(said) + "." if said else ""

    def lay_over_lesson(self, lesson: Any) -> Any:
        """The lesson plan's JSON with the wishes over its render profile."""
        changes = self.changes()
        style = lesson.get("style") if isinstance(lesson, dict) else None
        if not changes or not isinstance(style, dict):
            return lesson
        profile = style.get("render_profile")
        profile = _deep(profile if isinstance(profile, dict) else {}, changes)
        return {**lesson, "style": {**style, "render_profile": profile}}

    def lay_over_brief(self, brief: Any) -> Any:
        """The brief's JSON with the wishes over the profile changes it writes."""
        changes = self.changes()
        profile = brief.get("render_profile") if isinstance(brief, dict) else None
        if not changes or not isinstance(profile, dict):
            return brief
        written = {name: value for name, value in changes.items() if name in profile}
        return {**brief, "render_profile": _deep(profile, written)}


def _deep(below: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    """``below`` with ``over`` laid on it; nested tables are laid key by key."""
    result = dict(below)
    for name, value in over.items():
        under = result.get(name)
        both = isinstance(value, dict) and isinstance(under, dict)
        result[name] = _deep(under, value) if both else value  # type: ignore[arg-type]
    return result
