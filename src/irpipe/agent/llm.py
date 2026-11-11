"""The language model behind one interface (decision K10).

    client = LLM_CLIENTS.get("claude-cli")(settings)
    reply = client.complete(system, [Message("user", "Write build_ir.py for ...")])
    reply.text, reply.cost_usd

A client turns a system prompt and the conversation so far into the next
assistant message, as plain text. The agent's tool loop is ours (decision
K9): the model is given no tools of its provider's; it asks for one of
ours in its text (protocol.py). Changing the provider is one new file with
an ``@LLM_CLIENTS.register`` class; tests use a scripted client.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from irpipe.agent.settings import AgentSettings
from irpipe.core import PluginDefinitionError, Registry


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    text: str


@dataclass(frozen=True)
class Reply:
    """The model's next message, and what it cost when the client knows."""

    text: str
    cost_usd: float | None = None
    usage: dict[str, Any] = field(default_factory=dict)


class LLMError(RuntimeError):
    """The model could not be reached, or answered with an error instead of a message."""


class LLMClient(ABC):
    name: ClassVar[str]

    def __init__(self, settings: AgentSettings) -> None:
        self.settings = settings

    @abstractmethod
    def complete(self, system: str, messages: Sequence[Message]) -> Reply:
        """The assistant's next message after ``messages``; LLMError when there is none."""


def _check_client(cls: type[LLMClient]) -> None:
    if not getattr(cls, "name", ""):
        raise PluginDefinitionError(f"LLM client {cls.__name__} needs a `name`")


LLM_CLIENTS: Registry[type[LLMClient]] = Registry(
    "LLM client", key=lambda cls: cls.name, check=_check_client
)
"""The LLM clients, by name (pipeline.toml: ``[agent] provider``)."""
