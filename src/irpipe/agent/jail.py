"""Runs build_ir.py with limits: the inside of the agent's sandbox (analysis §4).

    python -I -B -m irpipe.agent.jail --cpu 120 --memory-mb 2048 build_ir.py

The script is run in the current folder (the run folder), as ``__main__``,
after two things are set up that it cannot undo:

- resource limits: CPU seconds, address space, the size of a file it
  writes, no core dumps;
- an audit hook (PEP 578) that refuses, with a PermissionError naming what
  was refused: network connections and name lookups; starting a program
  other than the ones measuring needs (latex, dvisvgm, fc-match, ldconfig); writing,
  removing or renaming anything outside the current folder (``/dev/null``
  aside); loading a C library by name through ctypes.

An audit hook is not a wall against code written to break out (a C
extension can do what it likes); it keeps an agent's mistakes inside the
run folder. Where the system allows it, sandbox.py also runs this under
bubblewrap, without a network and with only the run folder writable.
"""

import argparse
import os
import resource
import runpy
import sys
import traceback
from collections.abc import Iterable
from typing import Any

PROGRAMS = ("latex", "dvisvgm", "fc-match", "ldconfig")
"""What a script may start: what measuring a formula or a font runs, and what
ctypes.util.find_library asks (``ldconfig -p``) when Pango is loaded."""
FILE_LIMIT = 64 * 2**20
"""The largest file a script may write, in bytes."""
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
DENIED = {
    "socket.connect": "open a network connection",
    "socket.bind": "open a network port",
    "socket.sendto": "send over the network",
    "socket.sendmsg": "send over the network",
    "socket.getaddrinfo": "look up a network address",
    "socket.gethostbyname": "look up a network address",
    "socket.gethostbyaddr": "look up a network address",
    "os.system": "run a shell command",
    "os.exec": "start a program",
    "os.spawn": "start a program",
    "os.fork": "start a process",
    "os.forkpty": "start a process",
    "pty.spawn": "start a program",
}
"""Audit events refused outright, and what the refusal says the script tried."""
PATH_EVENTS = {
    "os.remove": (0,),
    "os.rmdir": (0,),
    "os.mkdir": (0,),
    "os.truncate": (0,),
    "os.chmod": (0,),
    "os.chown": (0,),
    "os.utime": (0,),
    "os.rename": (0, 1),
    "os.symlink": (1,),
    "os.link": (1,),
    "shutil.rmtree": (0,),
    "shutil.copyfile": (1,),
    "shutil.copytree": (1,),
}
"""Audit events that change the file system, and which of their arguments are paths."""


class Guard:
    """The audit hook: everything above, for a script run in ``folder``."""

    def __init__(self, folder: str, programs: Iterable[str] = PROGRAMS) -> None:
        self.folder = os.path.realpath(folder)
        self.programs = frozenset(programs)

    def __call__(self, event: str, args: tuple[Any, ...]) -> None:
        if event in DENIED:
            self.refuse(DENIED[event])
        elif event == "open":
            self.on_open(*args[:3])
        elif event in PATH_EVENTS:
            for k in PATH_EVENTS[event]:
                if k < len(args) and not self.inside(args[k]):
                    self.refuse(f"change {os.fsdecode(args[k])!s}, outside the run folder")
        elif event in ("subprocess.Popen", "os.posix_spawn"):
            program = args[0] if args[0] else (args[1][0] if args[1] else "")
            name = os.path.basename(os.fsdecode(program))
            if name not in self.programs:
                self.refuse(f"start the program {name!r}")
        elif event == "ctypes.dlopen" and args and args[0] is not None:
            self.refuse(f"load the C library {args[0]!r}")

    def on_open(self, path: Any, mode: Any, flags: Any) -> None:
        if path is None or isinstance(path, int):
            return
        writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
            isinstance(flags, int) and flags & WRITE_FLAGS
        )
        if writing and not self.inside(path):
            self.refuse(f"write {os.fsdecode(path)}, outside the run folder")

    def inside(self, path: Any) -> bool:
        if isinstance(path, int):
            return True  # a file descriptor: opening it was checked
        real = os.path.realpath(os.fsdecode(path))
        return real == os.devnull or real == self.folder or real.startswith(self.folder + os.sep)

    @staticmethod
    def refuse(what: str) -> None:
        raise PermissionError(f"the sandbox does not let build_ir.py {what}")


def limit(cpu_seconds: int, memory_mb: int) -> None:
    """Resource limits for this process and whatever it starts."""
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    memory = memory_mb * 2**20
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_FSIZE, (FILE_LIMIT, FILE_LIMIT))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="irpipe.agent.jail")
    parser.add_argument("--cpu", type=int, required=True, help="CPU seconds")
    parser.add_argument("--memory-mb", type=int, required=True)
    parser.add_argument("script")
    args = parser.parse_args(argv)
    limit(args.cpu, args.memory_mb)
    sys.addaudithook(Guard(os.getcwd()))
    sys.argv = [args.script]
    try:
        runpy.run_path(args.script, run_name="__main__")
    except SystemExit:
        raise
    except BaseException as error:  # the script's own error, without the jail's frames
        print(script_traceback(error, args.script), end="", file=sys.stderr)
        raise SystemExit(1) from None


def script_traceback(error: BaseException, script: str) -> str:
    """The traceback from the script's first frame on (only the message for a syntax error,
    which has no frame of the script's)."""
    tb = error.__traceback__
    while tb is not None and os.path.basename(tb.tb_frame.f_code.co_filename) != script:
        tb = tb.tb_next
    if tb is None:
        return "".join(traceback.format_exception_only(error))
    return "".join(traceback.format_exception(type(error), error, tb))


if __name__ == "__main__":
    main()
