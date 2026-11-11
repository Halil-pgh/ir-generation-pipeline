"""Where the agent's build_ir.py runs: no network, only its folder writable, limits (analysis §4).

    box = sandbox_for("auto", memory_mb=2048)
    ran = box.run(folder, timeout=120)            # ran.returncode, .stdout, .stderr, .timed_out
    command, env = box.command(folder, timeout)    # the same, for orchestrator.run_script

Two kinds, chosen in pipeline.toml (``[agent] sandbox``):

- ``bwrap``: bubblewrap runs the jail (jail.py) in new namespaces: no
  network, the whole system read-only, only the run folder writable, its
  own /tmp. It needs unprivileged user namespaces, which some systems
  switch off (Ubuntu's AppArmor does, unless bwrap has a profile);
- ``audit``: the jail alone: resource limits and an audit hook that refuses
  network, programs and writes outside the folder. It keeps an agent's
  mistakes in the folder; it is not a wall against hostile code.

``auto`` takes ``bwrap`` when it works on this machine and ``audit``
otherwise; ``none`` runs the script as step 19 does, with the user's rights.
Either way the script gets a clean environment (no secrets): PATH, a
language, and a home, a temporary folder and a cache inside the run folder
(``.sandbox/``), which is where LaTeX and fontconfig then write.
"""

import functools
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from irpipe.orchestrator.script import SCRIPT

type Kind = Literal["auto", "bwrap", "audit", "none"]

SCRATCH = ".sandbox"
"""The folder inside the run folder that holds the sandbox's home, /tmp and cache."""
SLACK = 5
"""CPU seconds the script gets beyond its time limit (the wall clock stops it first)."""


@dataclass(frozen=True)
class Ran:
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool
    seconds: float


@dataclass(frozen=True)
class Sandbox:
    kind: Literal["bwrap", "audit", "none"]
    memory_mb: int = 2048

    def command(self, folder: Path, timeout: float) -> tuple[list[str], dict[str, str]]:
        """The command that runs ``folder/build_ir.py`` (from ``folder``), and its environment."""
        folder = folder.resolve()
        if self.kind == "none":
            return [sys.executable, "-I", "-B", SCRIPT], dict(os.environ)
        jail = [
            sys.executable, "-I", "-B", "-m", "irpipe.agent.jail",
            "--cpu", str(int(timeout) + SLACK), "--memory-mb", str(self.memory_mb), SCRIPT,
        ]  # fmt: skip
        env = _environment(folder)
        if self.kind == "audit":
            return jail, env
        wrap = [
            "bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
            "--tmpfs", "/tmp", "--bind", str(folder), str(folder), "--unshare-all",
            "--die-with-parent", "--new-session", "--chdir", str(folder),
        ]  # fmt: skip
        return wrap + jail, env

    def run(self, folder: Path, timeout: float) -> Ran:
        """Run ``folder/build_ir.py`` in the sandbox; what it printed, and how it ended."""
        command, env = self.command(folder, timeout)
        started = time.perf_counter()
        try:
            done = subprocess.run(
                command, cwd=folder, env=env, capture_output=True, timeout=timeout, check=False
            )
        except subprocess.TimeoutExpired as expired:
            return Ran(None, _text(expired.stdout), _text(expired.stderr), True, timeout)
        seconds = time.perf_counter() - started
        return Ran(done.returncode, _text(done.stdout), _text(done.stderr), False, seconds)


def sandbox_for(kind: Kind, memory_mb: int = 2048) -> Sandbox:
    """The sandbox ``kind`` names; ``auto`` is bwrap where it works, else audit."""
    if kind == "auto":
        return Sandbox("bwrap" if bwrap_works() else "audit", memory_mb)
    return Sandbox(kind, memory_mb)


@functools.cache
def bwrap_works() -> bool:
    """Can bubblewrap make its namespaces on this machine?"""
    if shutil.which("bwrap") is None:
        return False
    probe = ["bwrap", "--ro-bind", "/", "/", "--unshare-all", "--die-with-parent", "true"]
    try:
        return subprocess.run(probe, capture_output=True, timeout=10, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _environment(folder: Path) -> dict[str, str]:
    scratch = folder / SCRATCH
    places = {"HOME": "home", "TMPDIR": "tmp", "XDG_CACHE_HOME": "cache"}
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"}
    for name, sub in places.items():
        (scratch / sub).mkdir(parents=True, exist_ok=True)
        env[name] = str(scratch / sub)
    return env


def _text(data: bytes | str | None) -> str:
    if data is None:
        return ""
    return data if isinstance(data, str) else data.decode(errors="replace")
