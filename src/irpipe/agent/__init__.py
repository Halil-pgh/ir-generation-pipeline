"""The IR agent (analysis §4, wave 2): a language model that writes build_ir.py with tools.

    result = run_agent(Path("brief.json"), Path("runs/projection"))

The model gets the brief and the locked header, writes build_ir.py with the
irkit SDK and checks it with the front-end's own functions; each submission
is compiled and drawn by the orchestrator, and the best one is kept. The
loop and the tools are ours (decision K9); the model is reached through
one interface (K10), first through ``claude -p``.

Module map:
    settings.py    AgentSettings: pipeline.toml's [agent]
    llm.py         LLMClient, Message, Reply, LLMError, LLM_CLIENTS
    claude_cli.py  "claude-cli": the model through claude -p
    protocol.py    one <call tool="..."> per message: parse()
    prompt.py      the system prompt, the first message, results
    reference.py   the IR's objects and fields, written from the models
    tools.py       run_python, validate, measure_text/tex, resolve, check, ask_planner
    sandbox.py     where build_ir.py runs: bwrap or the jail alone
    jail.py        limits and an audit hook around build_ir.py
    session.py     run_agent(): the loop, turns, the best turn, records
"""

from irpipe.agent import claude_cli as claude_cli
from irpipe.agent.llm import LLM_CLIENTS, LLMClient, LLMError, Message, Reply
from irpipe.agent.session import AgentError, AgentResult, Turn, run_agent
from irpipe.agent.settings import AgentSettings

__all__ = [
    "LLM_CLIENTS",
    "AgentError",
    "AgentResult",
    "AgentSettings",
    "LLMClient",
    "LLMError",
    "Message",
    "Reply",
    "Turn",
    "run_agent",
]
