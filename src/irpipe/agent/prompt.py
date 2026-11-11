"""What the agent is told: the system prompt, the first message, and how results come back.

    system = system_prompt(settings, example)
    first = first_message(inputs)
    wrap("check", result, calls_left=12, turns_left=2, limit=6000)

The system prompt is the same for every frame of a project, so the model's
provider can cache it: the role and the rules, the tools and the call
protocol, the irkit SDK (its module docstrings), the IR's objects and
fields (reference.py, from the models), and one whole build_ir.py as an
example (examples/tangents by default). What changes per frame, the brief,
its lesson and the locked header, is the first message.
"""

import inspect
import json
from types import ModuleType

from irpipe import irkit
from irpipe.agent.reference import object_reference
from irpipe.agent.settings import AgentSettings
from irpipe.irkit import errors, geometry, handles, measure, picture, shapes
from irpipe.orchestrator.inputs import Inputs

ROLE = """\
You are the IR agent of irpipe, a pipeline that draws one educational picture (a frame)
from a brief. You do not draw pixels and you do not write ir.json by hand: you write
build_ir.py, a Python script that works out every number and builds the picture with the
irkit SDK. The pipeline checks the picture, lays it out and draws it."""

PROTOCOL = """\
# How you work

You use the pipeline through tools. Every message you write holds exactly one tool call:

<call tool="NAME">BODY</call>

You may write a short note before the call: what you do next and why. The result comes
back in the next message as <result tool="NAME">...</result>, with the budget left.

Tools:
- run_python: BODY is the whole of build_ir.py, as plain Python (no Markdown fence). It
  replaces the previous script, runs it in a sandbox (no network; it may write only in its
  folder; the irkit SDK, the standard library and sympy are there) and validates the
  ir.json it wrote. Send the complete script every time.
- validate: no BODY. Schema, names and references of the current ir.json.
- measure_text: BODY {"text": "...", "size": "body", "weight": "regular", "italic": false}.
  The box the text will have, in frame units.
- measure_tex: BODY {"tex": "...", "size": "body"}: the box of a formula (the TeX between
  the dollars). A TeX mistake comes back as E-TEX.
- resolve: no BODY. Lays the picture out and lists where every object landed: the box it
  reaches, [left, bottom, right, top] in frame units.
- check: no BODY. Everything a submission is checked for before it is drawn: validate, the
  layout, the picture's checks (overlaps, safe area, contrast, text size...) and the
  brief's must_show coverage.
- submit: no BODY. Hands the current build_ir.py in; it must pass validate. The pipeline
  runs it again, compiles and draws the picture and reports back: a submission is a turn.
  The best turn is kept.
- ask_planner: BODY {"request": "shorten" | "split", "reason": "...", "items": [...]}.
  Ends the session and sends the frame back to the planner, who changes the brief:
  "shorten" asks for less (fewer must_show items, shorter texts), "split" for two frames
  instead of one. "items" names the must_show ids or texts that do not fit. Use it only
  when the brief cannot be met in this frame at readable sizes, after measuring and
  checking: never to avoid a warning you can fix.

A good session: run_python with a whole first script; read the result; check; fix with
run_python; check again; submit when check reports no errors and every warning is fixed or
allowed on purpose. Do not submit a script you have not checked."""

READY = """\
# What makes the picture READY

- no errors, and every warning fixed, or accepted with pic.allow(code, reason,
  objects=[...]) when it is meant (the reason says why);
- every must_show item of the brief is covered: the object or objects that show it say so
  with covers=["<item id>"];
- the brief's texts are used exactly as written (the title, the labels), and its focus
  items are the objects you give to pic.focus(...);
- the header is the orchestrator's: never change it (irkit writes it back as it was)."""

SCRIPT_RULES = """\
# Writing build_ir.py

- Begin with `pic = Picture.open()` (it reads header.json) and end with `pic.write()`.
- Work numbers out in Python, never by hand: Fraction keeps them exact (they reach the IR
  as "9/5"), and sympy is there for exact roots and angles. Use irkit.geometry for
  intersections, tangents, feet and seed points.
- Do not guess how big a text or formula is: measure it (pic.measure_text,
  pic.measure_tex, or the measure tools) and lay out from the safe area
  (pic.header.frame.safe: left, bottom, right, top).
- Things that belong together are placed by reference: a.tip, next_to=, at= an anchor.
- Keep everything inside the safe area; leave room between texts and lines.
- Print little: what the script prints comes back to you."""


def system_prompt(settings: AgentSettings, example: str | None) -> str:
    """The system prompt: the same for every frame, so the provider can cache it."""
    budget = f"You have {settings.max_turns} submissions and {settings.max_calls} messages in all."
    parts = [ROLE, PROTOCOL, budget, READY, SCRIPT_RULES, _frame_rules()]
    parts.append("# irkit, the SDK\n\n" + "\n\n".join(_docs(m) for m in IRKIT_MODULES))
    parts.append("# The IR: objects and their fields\n\n" + object_reference())
    if example:
        parts.append(
            "# An example: build_ir.py for another frame\n\n"
            "It shows the style: numbers worked out, sizes measured, the layout computed.\n\n"
            + example.strip()
        )
    return "\n\n".join(parts) + "\n"


IRKIT_MODULES: tuple[ModuleType, ...] = (irkit, picture, handles, shapes, geometry, measure, errors)


def _docs(module: ModuleType) -> str:
    return f"## {module.__name__}\n\n{inspect.getdoc(module) or ''}"


def _frame_rules() -> str:
    return """\
# The frame

Positions and lengths are in frame units: the short side of the frame is 9 units, the
origin is its center, y points up. Type sizes, stroke widths and dashes are in reference
pixels: 120 of them make one unit. The header gives the frame's size (frame.units), its
safe area (frame.safe), the type size of each role (typography.sizes), the concept colors
(colors: use them by name) and the style classes (styles: "muted", "construction")."""


def first_message(inputs: Inputs) -> str:
    """The frame to draw: its brief, its lesson's notes when it has one, and the header."""
    brief = inputs.brief.model_dump_json(indent=2, exclude_none=True)
    parts = ["Draw the frame this brief describes.", f"<brief>\n{brief}\n</brief>"]
    lesson = inputs.lesson
    if lesson is not None:
        notes = {
            "topic": lesson.topic,
            "goals": lesson.goals,
            "misconceptions": lesson.misconceptions,
            "frames": [f"{f.id} ({f.purpose}): {f.summary}" for f in lesson.frames],
            "notation": lesson.style.notation,
        }
        parts.append(f"<lesson>\n{json.dumps(notes, indent=2, ensure_ascii=False)}\n</lesson>")
    locked = inputs.header.model_dump_json(indent=2, exclude_none=True)
    parts.append(f"<header>\n{locked}\n</header>\n(Picture.open() reads it from header.json.)")
    parts.append("Begin by writing the whole build_ir.py with run_python.")
    return "\n\n".join(parts)


def wrap(tool: str, result: str, *, calls_left: int, turns_left: int, limit: int) -> str:
    """A tool's result as the next user message: cut to ``limit`` characters, with the budget."""
    if len(result) > limit:
        result = result[:limit] + f"\n… ({len(result) - limit} more characters cut)"
    budget = f"(messages left: {calls_left}, submissions left: {turns_left})"
    return f'<result tool="{tool}">\n{result}\n</result>\n{budget}'
