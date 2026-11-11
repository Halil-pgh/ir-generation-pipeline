"""LLM client "claude-cli": the model through ``claude -p``, on the team's subscription (K9).

    claude -p --tools "" --system-prompt-file system.md --output-format json
              --model claude-haiku-5-5 --no-session-persistence ...   < conversation

Claude Code's print mode is used as a plain completion: none of its own
tools, no MCP servers, no slash commands, none of the user's or the
project's settings, no saved session, and a system prompt of ours alone;
the loop and the tools are the agent's (K9). It runs in an empty temporary
folder with a clean environment (PATH, HOME for the login, the language),
so nothing from this repository or the shell reaches it but what the
agent sends.

Print mode takes one prompt, so a conversation of several messages is
written out as a transcript, oldest first, and the model is asked for the
assistant's next message. The JSON result carries the reply, its cost and
token usage; an error result, a failed command or a timeout is an LLMError.
"""

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from irpipe.agent.llm import LLM_CLIENTS, LLMClient, LLMError, Message, Reply

COMMAND = "claude"
KEPT_ENVIRONMENT = ("PATH", "HOME", "USER", "LANG", "LC_ALL", "XDG_CONFIG_HOME")
"""What the command keeps of the environment: enough to find itself and the login."""


@LLM_CLIENTS.register
class ClaudeCLI(LLMClient):
    name = "claude-cli"

    def complete(self, system: str, messages: Sequence[Message]) -> Reply:
        if shutil.which(COMMAND) is None:
            raise LLMError(f"'{COMMAND}' is not installed or not on PATH")
        with tempfile.TemporaryDirectory(prefix="irpipe-llm-") as folder:
            prompt_file = Path(folder) / "system.md"
            prompt_file.write_text(system, encoding="utf-8")
            try:
                done = subprocess.run(
                    self.command(prompt_file),
                    input=transcript(messages),
                    capture_output=True,
                    text=True,
                    cwd=folder,
                    env={k: v for k, v in os.environ.items() if k in KEPT_ENVIRONMENT},
                    timeout=self.settings.call_timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                raise LLMError(
                    f"the model gave no reply in {self.settings.call_timeout:g} s"
                ) from None
        return parse_result(done.returncode, done.stdout, done.stderr)

    def command(self, prompt_file: Path) -> list[str]:
        command = [
            COMMAND, "-p", "--tools", "", "--system-prompt-file", str(prompt_file),
            "--output-format", "json", "--no-session-persistence", "--strict-mcp-config",
            "--disable-slash-commands", "--setting-sources", "",
        ]  # fmt: skip
        if self.settings.model:
            command += ["--model", self.settings.model]
        if self.settings.effort:
            command += ["--effort", self.settings.effort]
        return command


def transcript(messages: Sequence[Message]) -> str:
    """The conversation as one prompt: a single message as it is, several as a transcript."""
    if len(messages) == 1:
        return messages[0].text
    parts = [
        "The conversation so far, oldest first. You are the assistant: write the "
        "assistant's next message, and only that.\n"
    ]
    parts += [f'<message from="{m.role}">\n{m.text}\n</message>' for m in messages]
    return "\n\n".join(parts) + "\n"


def parse_result(returncode: int, stdout: str, stderr: str) -> Reply:
    """The reply in ``claude -p --output-format json``'s result; LLMError for anything else."""
    try:
        data: dict[str, Any] = json.loads(stdout)
    except json.JSONDecodeError:
        said = (stderr or stdout).strip().splitlines()[-3:]
        raise LLMError(
            f"{COMMAND} -p failed (exit {returncode}): " + " / ".join(said or ["no output"])
        ) from None
    if data.get("is_error") or data.get("subtype") != "success":
        detail = data.get("result") or data.get("api_error_status") or data.get("subtype")
        raise LLMError(f"the model answered with an error: {detail}")
    text = data.get("result")
    if not isinstance(text, str):
        raise LLMError("the model's result holds no text")
    cost = data.get("total_cost_usd")
    usage = data.get("usage")
    return Reply(
        text,
        float(cost) if isinstance(cost, int | float) else None,
        usage if isinstance(usage, dict) else {},
    )
