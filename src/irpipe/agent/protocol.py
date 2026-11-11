"""How the model asks for a tool: one tagged call in its message (decision K9: our harness).

    I will measure the formula first.
    <call tool="measure_tex">{"tex": "\\\\frac{a}{b}", "size": "body"}</call>

    <call tool="run_python">
    from irpipe.irkit import Picture
    ...
    </call>

A message holds at most one call: text before it is the model's own notes,
and stays in the conversation. The body is the tool's input as it is:
Python for run_python, a JSON object for the tools that take arguments,
nothing for the others. A Markdown code fence around the body is taken
off, and so is a stray closing tag of another tool format on its last line
(``</parameter>``: a model used to its provider's own tool calls writes
one now and then; no Python script ends with it). A message without a
call, with an unclosed one or with more than one gets an answer that says
so (only the first of several runs).
"""

import re
from dataclasses import dataclass

CALL = re.compile(r'<call\s+tool="([A-Za-z_]+)"\s*>(.*?)</call>', re.DOTALL)
OPENED = re.compile(r'<call\s+tool="([A-Za-z_]+)"\s*>')
FENCE = re.compile(r"^```[A-Za-z0-9_+-]*\n(.*?)\n?```$", re.DOTALL)
STRAY = re.compile(r"\n\s*</[A-Za-z_:]+>\s*$")


@dataclass(frozen=True)
class Call:
    tool: str
    body: str


@dataclass(frozen=True)
class Parsed:
    call: Call | None
    problem: str | None = None
    """What was wrong with the message: no call, an unclosed one, or several."""


def parse(message: str) -> Parsed:
    """The call in ``message``, and a note when the message did not keep to the protocol."""
    found = CALL.findall(message)
    if not found:
        opened = OPENED.search(message)
        if opened:
            return Parsed(
                None,
                f"the call to {opened.group(1)} was not closed with </call>; it may have been "
                "cut off: send it again, shorter if it is long",
            )
        return Parsed(
            None,
            'your message holds no tool call; write exactly one, as <call tool="NAME">...</call>',
        )
    tool, body = found[0]
    note = None
    if len(found) > 1:
        note = f"your message held {len(found)} calls; only the first ({tool}) ran: one per message"
    return Parsed(Call(tool, unfence(body.strip())), note)


def unfence(body: str) -> str:
    """``body`` without a Markdown code fence around it, or a stray closing tag after it."""
    body = STRAY.sub("", body)
    match = FENCE.match(body)
    return match.group(1) if match else body
