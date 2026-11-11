"""The planner's settings: pipeline.toml's ``[planner]`` table.

    settings = PlannerSettings.from_config(config)     # defaults for what the table leaves out

    [planner]
    provider = "claude-cli"       # the LLM client (irpipe/agent/llm.py's registry)
    model = "claude-sonnet-5-5"   # a stronger model than the agent's (analysis, question 8)
    max_answers = 3               # answers per plan or revision; each one is checked
    max_frames = 6                # frames a lesson may have
    max_returns = 2               # times a lesson sends one frame back to the planner

The planner reaches its model through the agent's LLM clients (one
interface, K10), so the client is given the agent's settings type with the
planner's provider, model, effort and time limit.
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from irpipe.agent.settings import AgentSettings
from irpipe.core import PipelineConfig
from irpipe.core.errors import PipelineConfigError


class PlannerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = "claude-cli"
    """The LLM client, by its registered name."""
    model: str = "claude-sonnet-5-5"
    """The model the client asks for; "" for its default."""
    effort: Literal["", "low", "medium", "high", "xhigh", "max"] = ""
    """How hard the model thinks, where the client supports it; "" for its default."""
    call_timeout: float = Field(default=600, gt=0)
    """Seconds one answer may take: a whole lesson is written in one answer."""
    max_answers: int = Field(default=3, ge=1, le=10)
    """Answers per plan or revision; an answer with problems is sent back with them."""
    max_frames: int = Field(default=6, ge=1, le=20)
    """Frames a lesson may have, also after a frame is split."""
    max_returns: int = Field(default=2, ge=0, le=10)
    """Times a lesson sends one frame (and the frames split from it) back to the planner."""
    example: str = "examples/projection"
    """A folder whose lesson_plan.json and brief.json the system prompt shows (relative to
    pipeline.toml); "" for none."""

    @classmethod
    def from_config(cls, config: PipelineConfig) -> Self:
        try:
            return cls.model_validate(config.planner)
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors()
            )
            raise PipelineConfigError(f"[planner]: {problems}") from exc

    def client_settings(self) -> AgentSettings:
        """What the LLM client reads: the provider, model, effort and time limit."""
        return AgentSettings(
            provider=self.provider,
            model=self.model,
            effort=self.effort,
            call_timeout=self.call_timeout,
        )
