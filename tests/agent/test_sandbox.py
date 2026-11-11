"""The sandbox: what build_ir.py may and may not do, its limits and its environment."""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from irpipe.agent import sandbox as sandbox_module
from irpipe.agent.jail import Guard
from irpipe.agent.sandbox import Sandbox, sandbox_for

ROOT = Path(__file__).parent.parent.parent


def run(tmp_path: Path, code: str, timeout: float = 60) -> sandbox_module.Ran:
    folder = tmp_path / "run"
    folder.mkdir(exist_ok=True)
    (folder / "build_ir.py").write_text(code, encoding="utf-8")
    return Sandbox("audit").run(folder, timeout)


def test_an_irkit_script_runs_measures_and_writes_in_its_folder(
    tmp_path: Path, header: dict[str, Any]
) -> None:
    (tmp_path / "run").mkdir()
    (tmp_path / "run" / "header.json").write_text(json.dumps(header), encoding="utf-8")
    code = (
        "from irpipe.irkit import Picture\npic = Picture.open()\n"
        "print(round(pic.measure_tex('x^2').width, 2))\n"
        "pic.circle('c', center=(0, 0), radius=1)\npic.write()\n"
    )
    ran = run(tmp_path, code)
    assert ran.returncode == 0, ran.stderr
    assert (tmp_path / "run" / "ir.json").exists() and float(ran.stdout) > 0
    assert (tmp_path / "run" / ".sandbox" / "cache").is_dir()  # LaTeX's cache stays inside


@pytest.mark.parametrize(
    ("code", "refused"),
    [
        ("open({outside!r}, 'w')", "write {outside}, outside the run folder"),
        ("import os\nos.remove({outside!r})", "change {outside}, outside the run folder"),
        ("import os\nos.rename('build_ir.py', {outside!r})", "outside the run folder"),
        ("import socket\nsocket.create_connection(('1.1.1.1', 53), timeout=2)", "network"),
        ("import subprocess\nsubprocess.run(['ls'])", "start the program 'ls'"),
        ("import os\nos.system('true')", "run a shell command"),
        ("import ctypes\nctypes.CDLL('libc.so.6')", "load the C library 'libc.so.6'"),
    ],
)
def test_what_reaches_outside_the_folder_is_refused(
    tmp_path: Path, code: str, refused: str
) -> None:
    outside = str(tmp_path / "outside.txt")
    (tmp_path / "outside.txt").write_text("keep")
    ran = run(tmp_path, code.format(outside=outside))
    assert ran.returncode != 0
    assert "PermissionError: the sandbox does not let build_ir.py " in ran.stderr
    assert refused.format(outside=outside) in ran.stderr
    assert (tmp_path / "outside.txt").read_text() == "keep"


def test_the_environment_holds_no_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    ran = run(tmp_path, "import os, json\nprint(json.dumps(sorted(os.environ)))\n")
    names = set(json.loads(ran.stdout)) - {"LC_CTYPE"}  # Python may set LC_CTYPE itself
    assert names == {"PATH", "LANG", "HOME", "TMPDIR", "XDG_CACHE_HOME"}


def test_a_script_that_runs_too_long_or_takes_too_much_memory_is_stopped(tmp_path: Path) -> None:
    assert run(tmp_path, "while True: pass\n", timeout=1).timed_out
    ran = run(tmp_path, "x = bytearray(4 * 2**30)\n")
    assert ran.returncode != 0 and "MemoryError" in ran.stderr


def test_the_guard_tells_writing_from_reading() -> None:
    guard = Guard("/work/run")
    guard("open", ("/etc/hostname", "r", os.O_RDONLY))
    guard("open", ("/work/run/ir.json", "w", os.O_WRONLY | os.O_CREAT))
    guard("open", (os.devnull, "w", os.O_WRONLY))
    with pytest.raises(PermissionError, match="write /work/runner/x"):
        guard("open", ("/work/runner/x", None, os.O_RDWR))
    guard("subprocess.Popen", ("/usr/bin/latex", ["latex"], None, None))
    with pytest.raises(PermissionError, match="start the program 'sh'"):
        guard("os.posix_spawn", ("/bin/sh", ["sh", "-c", "x"], {}))


def test_auto_takes_bwrap_only_where_it_works(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sandbox_module, "bwrap_works", lambda: False)
    assert sandbox_for("auto").kind == "audit"
    monkeypatch.setattr(sandbox_module, "bwrap_works", lambda: True)
    assert sandbox_for("auto", memory_mb=512) == Sandbox("bwrap", 512)
    folder = tmp_path.resolve()
    command, env = Sandbox("bwrap").command(folder, 30)
    assert command[:1] == ["bwrap"] and "--unshare-all" in command
    assert command[command.index("--bind") + 1] == str(folder)
    jail = ["irpipe.agent.jail", "--cpu", "35", "--memory-mb", "2048", "build_ir.py"]
    assert command[-6:] == jail
    assert env["HOME"] == str(folder / ".sandbox" / "home")
