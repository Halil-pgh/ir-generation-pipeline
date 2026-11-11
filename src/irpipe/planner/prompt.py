"""What the planner is told: the system prompt, the first message of a plan or a revision,
and the problems of an answer.

    system = system_prompt(settings, example)
    first = plan_message("vector projection", wishes)
    first = revise_message(request, lesson_text, brief_text, wishes)
    again = problems_message(["frame 'recap' of the lesson plan has no brief"])

The system prompt is the same for every lesson, so the provider can cache
it: the role, the rules of a good lesson and a good brief, the answer's
format, what the project offers (aspects, platforms, type scales, font
pairs), the JSON Schemas of the lesson plan and the brief, and a lesson
plan with one of its briefs as an example (examples/projection by default).
"""

import json
from pathlib import Path

from irpipe.orchestrator.inputs import FONT_PAIRS, LESSON_FILE
from irpipe.planner.settings import PlannerSettings
from irpipe.planner.wishes import Wishes
from irpipe.platforms import PLATFORMS
from irpipe.schema.brief import FrameBrief, LessonPlan
from irpipe.schema.render_profile import ASPECT_PRESETS, SCALE_PRESETS
from irpipe.schema.request import PlannerRequest

ROLE = """\
You are the planner of irpipe, a pipeline that makes the pictures (frames) of a short lesson.
From a topic you plan the lesson, and for each frame you write a brief: what that one picture
must show, in words a program can check. You do not draw. The IR agent draws each frame from
its brief with a program that computes, measures and checks; it cannot add what the brief
leaves out, and it cannot make room for more than one picture holds."""

LESSON_RULES = """\
# The lesson

- A lesson is a few frames told in order, each with one purpose: "introduce" brings an idea
  in, "define" defines it, "example" shows a case of it, "counterexample" shows what it is
  not (or meets a misconception), "summary" sums up. Begin with introduce or define; end with
  a summary when there are three frames or more.
- Goals say what the learner can do afterwards; misconceptions are what learners often get
  wrong, for some frame to meet.
- The style holds what stays the same through the lesson: one color per concept
  (concept_colors), how each concept is written in TeX (notation), and the render profile.
  A concept keeps its color in every frame. Colors stand out from the background and from
  each other; give them as "#RRGGBB"."""

BRIEF_RULES = """\
# A brief

- One idea per frame. A frame is a picture, not a page: two to six must_show items, a title
  of a few words, short labels, at most one formula of moderate length, and no paragraph.
  Text besides the title and labels is at most about twelve words.
- must_show items have short ids (a letter, then letters, digits or _). Each says what is
  shown in plain words; when it has numbers, give them in data, chosen so the picture reads
  well: vectors not nearly parallel, angles not tiny, values with exact, simple results.
- focus names the must_show items the eye should go to first.
- texts are used exactly as written: the title, the labels (label name -> its words; a
  label in math is TeX without dollars, such as "\\\\theta") and, with a burnt-in subtitle,
  the subtitle. Every text is in the lesson's language (render_profile.typography.lang).
- constraints.must are checked strictly; constraints.should are wishes.
- composition_notes describe the picture in words: what goes where, what stands out.
- A brief belongs to its lesson ("lesson": the lesson plan's id), has its frame's id and
  purpose, and changes the lesson's style only where the frame needs it.
- The frame: its short side is 9 units, so a 16:9 frame is 16 by 9 units and a 9:16 frame
  9 by 16. Body text is about 0.35 units high ("comfortable" scale), and a line of 40
  characters of body text is about 7 units wide. Margins, platform overlays and a subtitle
  band take room from the edges."""

ANSWER = """\
# Your answer

Answer with one JSON object and nothing else (a ```json fence around it is fine):

{"lesson_plan": {...}, "briefs": [{...}, ...]}

lesson_plan follows the lesson plan's schema; briefs holds one brief per frame of the lesson
plan, in its order, each following the brief's schema. Every answer is read as the pipeline
reads it; when something is wrong, the problems come back and you answer again with the
whole object.

# When a frame comes back

A frame comes back when it cannot be drawn as its brief asks. You get the lesson plan, the
frame's brief and a request:
- "shorten": keep the frame and its id, and ask for less: fewer must_show items, shorter
  texts, simpler data. The other frames stay as they are.
- "split": the frame holds too much for one picture. Put two frames, under new ids, where it
  was in the lesson plan, the other frames as they were, and write both briefs.
- "fix": the brief or the lesson plan is wrong; the problems say how. Keep the frame's id.
Answer in the same format, with the whole lesson plan and only the briefs you changed or
added; the briefs you leave out are kept."""


def system_prompt(settings: PlannerSettings, example: tuple[str, str] | None) -> str:
    """The system prompt: the same for every lesson, so the provider can cache it."""
    parts = [ROLE, LESSON_RULES, BRIEF_RULES, ANSWER, _offers(settings), _schemas()]
    if example is not None:
        lesson, brief = example
        parts.append(
            "# An example: a lesson plan and the brief of one of its frames\n\n"
            f"{LESSON_FILE}:\n{lesson.strip()}\n\nThe brief of frame "
            f'"{json.loads(brief).get("id")}":\n{brief.strip()}'
        )
    return "\n\n".join(parts) + "\n"


def read_example(folder: Path) -> tuple[str, str] | None:
    """The example folder's lesson plan and brief, when both are there."""
    lesson, brief = folder / LESSON_FILE, folder / "brief.json"
    if not (lesson.exists() and brief.exists()):
        return None
    return lesson.read_text(encoding="utf-8"), brief.read_text(encoding="utf-8")


def _offers(settings: PlannerSettings) -> str:
    aspects = "; ".join(f"{name} ({p.typical_use})" for name, p in ASPECT_PRESETS.items())
    platforms = "; ".join(
        f"{name} ({PLATFORMS.get(name).description}"
        + (f", {PLATFORMS.get(name).aspect} only)" if PLATFORMS.get(name).aspect else ")")
        for name in PLATFORMS.names()
    )
    scales = "; ".join(
        f"{name} (body {sizes.body:g} px, title {sizes.title:g} px)"
        for name, sizes in SCALE_PRESETS.items()
    )
    fonts = "; ".join(f"text {text!r} with math {math!r}" for text, math in sorted(FONT_PAIRS))
    return f"""\
# What the project offers

- At most {settings.max_frames} frames a lesson.
- Aspects: {aspects}. Any other W:H between 1:4 and 4:1 works too.
- Platforms (render_profile.platform): {platforms}.
- Type scales (render_profile.typography.scale): {scales}.
- Font pairs (render_profile.typography.font_pair): {fonts}; no other.
- Subtitles (render_profile.subtitle.mode): "none"; "reserve" keeps a band free for
  subtitles added later; "burn_in" draws texts.subtitle into it."""


def _schemas() -> str:
    def schema(model: type[LessonPlan] | type[FrameBrief]) -> str:
        return json.dumps(model.model_json_schema(), separators=(",", ":"), ensure_ascii=False)

    return (
        "# The schemas\n\n"
        f"The lesson plan (lesson_plan):\n{schema(LessonPlan)}\n\n"
        f"A brief (each of briefs):\n{schema(FrameBrief)}"
    )


def plan_message(topic: str, wishes: Wishes) -> str:
    """The first message of a plan: the topic, and what the user asked for."""
    parts = [f"Plan a lesson on this topic, and write the brief of each of its frames.\n\n"
             f"<topic>\n{topic.strip()}\n</topic>"]  # fmt: skip
    if wishes.describe():
        parts.append(wishes.describe() + " This is not yours to change.")
    parts.append('Answer with the JSON object {"lesson_plan": ..., "briefs": [...]}.')
    return "\n\n".join(parts)


WHAT_TO_DO = {
    "shorten": "Frame {frame!r} cannot be drawn as its brief asks: keep the frame and its id, "
    "and ask for less (fewer must_show items, shorter texts, simpler data).",
    "split": "Frame {frame!r} holds too much for one picture: put two frames, under new ids, "
    "where it was in the lesson plan, and write both briefs.",
    "fix": "The brief of frame {frame!r}, or the lesson plan, is wrong; the problems say how. "
    "Fix it and keep the frame's id.",
}


def revise_message(request: PlannerRequest, lesson: str, brief: str, wishes: Wishes) -> str:
    """The first message of a revision: the lesson plan, the frame's brief and the request."""
    asked = request.model_dump_json(indent=2, exclude_defaults=True)
    parts = [
        WHAT_TO_DO[request.kind].format(frame=request.frame),
        f"<lesson_plan>\n{lesson.strip()}\n</lesson_plan>",
        f"<brief>\n{brief.strip()}\n</brief>",
        f"<request>\n{asked}\n</request>",
    ]
    if wishes.describe():
        parts.append(wishes.describe() + " This is not yours to change.")
    parts.append(
        'Answer with the JSON object {"lesson_plan": ..., "briefs": [...]}: the whole lesson '
        "plan, and only the briefs you changed or added."
    )
    return "\n\n".join(parts)


def problems_message(problems: list[str]) -> str:
    """An answer's problems, sent back; nothing of that answer is kept."""
    lines = "\n".join(f"- {problem}" for problem in problems)
    return (
        f"Your answer cannot be used yet; nothing of it was kept:\n{lines}\n\n"
        "Answer again with the whole JSON object, every problem fixed."
    )
