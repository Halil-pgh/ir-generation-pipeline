"""What goes back to the planner: a request to change one frame's brief (analysis §1).

    request = PlannerRequest(frame="projection", kind="split", reason="...", items=("formula",))

When a frame cannot be drawn as its brief asks, the planner changes the
brief; the agent does not squeeze the picture to make it fit (analysis §1,
"Planner'a geri dönüş yolu"). There are three kinds of request:

- ``shorten``: keep the frame, ask for less: fewer must_show items, shorter texts;
- ``split``: make it two frames, told one after the other in the lesson;
- ``fix``: the brief or the lesson plan is wrong (E-BRIEF); ``issues`` say how.

The agent asks for ``shorten`` or ``split`` with its ``ask_planner`` tool;
the orchestrator's E-BRIEF issues become a ``fix`` request. The planner
answers with the lesson plan and the briefs it changed (irpipe/planner).
"""

from typing import Annotated, Final, Literal

from pydantic import Field

from irpipe.schema.base import StrictModel
from irpipe.schema.ir.common import Name

REQUEST_VERSION: Final = "planner-request/1.0"

Kind = Literal["shorten", "split", "fix"]

Text = Annotated[str, Field(min_length=1)]


class PlannerRequest(StrictModel):
    """planner_request.json: one frame, what should change and why."""

    version: Literal["planner-request/1.0"] = REQUEST_VERSION
    frame: Name
    """The frame's id, as the lesson plan lists it."""
    kind: Kind
    reason: Text
    """Why, in plain words: what does not fit, and where."""
    items: tuple[Text, ...] = ()
    """The must_show ids or texts that do not fit (shorten, split)."""
    issues: tuple[Text, ...] = ()
    """The open issues that sent the frame back, one line each (fix)."""
