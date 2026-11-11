"""The agent's settings: pipeline.toml's ``[agent]`` table.

    settings = AgentSettings.from_config(config)     # defaults for what the table leaves out

    [agent]
    provider = "claude-cli"     # the LLM client (llm.py's registry)
    model = "claude-haiku-5-5"  # what the client asks for; "" leaves it to the client
    max_turns = 3               # submissions: each one is compiled and drawn
    max_calls = 30              # replies the model may write in one session
    sandbox = "auto"            # where build_ir.py runs (sandbox.py)

A misspelled key fails when the agent starts, with the closest name.
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from irpipe.core import PipelineConfig
from irpipe.core.errors import PipelineConfigError


class AgentSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = "claude-cli"
    """The LLM client, by its registered name."""
    model: str = "claude-haiku-5-5"
    """The model the client asks for (analysis §4: a small, fast model); "" for its default."""
    effort: Literal["", "low", "medium", "high", "xhigh", "max"] = ""
    """How hard the model thinks, where the client supports it; "" for its default."""
    max_turns: int = Field(default=3, ge=1, le=10)
    """Submissions per session; each is compiled, drawn and reported back (analysis §1)."""
    max_calls: int = Field(default=30, ge=1, le=200)
    """Replies the model may write in one session, tool calls and submissions together."""
    call_timeout: float = Field(default=300, gt=0)
    """Seconds one reply may take."""
    script_timeout: float = Field(default=120, gt=0)
    """Seconds build_ir.py may run (as in the orchestrator, K134)."""
    sandbox: Literal["auto", "bwrap", "audit", "none"] = "auto"
    memory_mb: int = Field(default=2048, ge=256)
    """The address space build_ir.py may use."""
    result_chars: int = Field(default=6000, ge=500)
    """How much of a tool's output goes back to the model; the rest is cut, saying so."""
    example: str = "examples/tangents/build_ir.py"
    """A whole build_ir.py the system prompt shows (relative to pipeline.toml); "" for none."""

    @classmethod
    def from_config(cls, config: PipelineConfig) -> Self:
        try:
            return cls.model_validate(config.agent)
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors()
            )
            raise PipelineConfigError(f"[agent]: {problems}") from exc
