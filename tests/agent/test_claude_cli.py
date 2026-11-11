"""The "claude-cli" client against a stand-in ``claude`` command: what it runs, what it reads."""

import json
import os
import re
import stat
from pathlib import Path

import pytest

from irpipe.agent import AgentSettings, LLMError, Message
from irpipe.agent.claude_cli import ClaudeCLI, transcript

RESULT = {
    "type": "result", "subtype": "success", "is_error": False,
    "result": '<call tool="check"></call>', "total_cost_usd": 0.0021,
    "usage": {"input_tokens": 12, "output_tokens": 7},
}  # fmt: skip


def stand_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    """A ``claude`` on PATH that runs ``body`` (shell) instead of asking a model."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    command = bin_dir / "claude"
    command.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    command.chmod(command.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


def test_it_asks_for_a_plain_completion_and_reads_the_json_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stand_in(
        tmp_path, monkeypatch,
        f'printf "%s\\n" "$@" > {tmp_path}/args; cat > {tmp_path}/stdin; env > {tmp_path}/env\n'
        f'cat "$(grep -A1 -- --system-prompt-file {tmp_path}/args | tail -1)" > {tmp_path}/system\n'
        f"echo '{json.dumps(RESULT)}'",
    )  # fmt: skip
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not for the model")
    monkeypatch.setenv("CLAUDECODE", "1")
    client = ClaudeCLI(AgentSettings(model="claude-haiku-5-5", effort="low"))
    reply = client.complete("the system prompt", [Message("user", "draw it")])
    assert (reply.text, reply.cost_usd, reply.usage["output_tokens"]) == (
        RESULT["result"],
        0.0021,
        7,
    )
    args = (tmp_path / "args").read_text().splitlines()
    assert args[:3] == ["-p", "--tools", ""]
    for flag in ("--no-session-persistence", "--strict-mcp-config", "--disable-slash-commands"):
        assert flag in args
    assert args[args.index("--setting-sources") + 1] == ""
    assert args[args.index("--output-format") + 1] == "json"
    assert args[args.index("--model") + 1] == "claude-haiku-5-5"
    assert args[args.index("--effort") + 1] == "low"
    assert (tmp_path / "system").read_text() == "the system prompt"
    assert (tmp_path / "stdin").read_text() == "draw it"
    env = (tmp_path / "env").read_text()
    assert "ANTHROPIC_API_KEY" not in env and "CLAUDECODE" not in env and "HOME=" in env


def test_a_conversation_is_sent_as_a_transcript() -> None:
    messages = [Message("user", "draw it"), Message("assistant", "<call>"), Message("user", "ok")]
    text = transcript(messages)
    assert text.startswith("The conversation so far, oldest first. You are the assistant")
    assert '<message from="assistant">\n<call>\n</message>' in text
    assert text.rstrip().endswith('<message from="user">\nok\n</message>')


@pytest.mark.parametrize(
    ("body", "said"),
    [
        ("echo 'not logged in' >&2; exit 1", "claude -p failed (exit 1): not logged in"),
        ("echo '{\"subtype\": \"success\", \"is_error\": true, \"result\": \"limit reached\"}'",
         "answered with an error: limit reached"),
        ("echo '{\"subtype\": \"error_max_turns\", \"is_error\": false}'", "error_max_turns"),
        ("sleep 5", "no reply in 0.5 s"),
    ],
)  # fmt: skip
def test_a_failure_is_an_llm_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str, said: str
) -> None:
    stand_in(tmp_path, monkeypatch, body)
    client = ClaudeCLI(AgentSettings(call_timeout=0.5))
    with pytest.raises(LLMError, match=re.escape(said)):
        client.complete("system", [Message("user", "hi")])


def test_a_missing_command_is_an_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/nonexistent")
    with pytest.raises(LLMError, match="not installed"):
        ClaudeCLI(AgentSettings()).complete("system", [Message("user", "hi")])
