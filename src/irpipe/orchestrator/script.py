"""Running the agent's build_ir.py, which writes ir.json (analysis §4).

    issues = run_script(folder, timeout=60)

The script is run in the run folder, by the pipeline's own Python. There it
finds ``header.json``, the header the orchestrator locked; it adds the body
(computing its numbers, not copying them) and writes the whole picture to
``ir.json``. A script that stops with an error, runs too long or writes no
ir.json is the agent's to fix: E-SCRIPT, with the end of its own traceback.

It runs with the rights of whoever started the pipeline: the sandbox for
code an LLM wrote comes with the agent (step 21).
"""

import subprocess
import sys
from pathlib import Path
from typing import Final

from irpipe.core import ISSUE_CODES, Issue, IssueCode, Origin

E_SCRIPT = ISSUE_CODES.register(
    IssueCode("E-SCRIPT", Origin.IR, "the agent's build_ir.py did not write ir.json")
)

SCRIPT: Final = "build_ir.py"
HEADER: Final = "header.json"
IR: Final = "ir.json"
TRACEBACK_LINES = 6


def run_script(folder: Path, timeout: float) -> list[Issue]:
    """Run ``folder/build_ir.py`` there; the issue when it does not write ``folder/ir.json``."""
    (folder / IR).unlink(missing_ok=True)
    command = [sys.executable, "-I", "-B", SCRIPT]
    try:
        run = subprocess.run(command, cwd=folder, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return [
            E_SCRIPT(
                f"{SCRIPT} ran for more than {timeout:g} s and was stopped",
                hint="look for a loop that does not end, or work that can be done once",
            )
        ]
    if run.returncode != 0:
        said = run.stderr.decode(errors="replace").strip().splitlines()[-TRACEBACK_LINES:]
        return [
            E_SCRIPT(
                f"{SCRIPT} stopped with an error: " + " / ".join(line.strip() for line in said),
                hint=f"fix {SCRIPT}; the error and the line above are its own",
            )
        ]
    if not (folder / IR).exists():
        return [
            E_SCRIPT(
                f"{SCRIPT} ran but wrote no {IR}",
                hint=f"read the header from {HEADER}, add the body and write both to {IR}",
            )
        ]
    return []
