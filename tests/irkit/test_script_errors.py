"""A mistake in build_ir.py comes back as E-SCRIPT with the script's own line in the message.

The orchestrator keeps only the end of a script's traceback, so the SDK must
not fill that end with its own lines. The scripts here run as the
orchestrator runs them (run_script), in a folder with a header.json.
"""

import json
import traceback
from pathlib import Path
from typing import Any

import pytest

from irpipe.irkit.errors import ScriptValueError, at_the_call
from irpipe.orchestrator.script import run_script

SCRIPT = """\
from irpipe.irkit import Picture, label
pic = Picture.open()
a = pic.line("a", start=(0, 0), end=(1, 1))
{mistake}
pic.write()
"""
MISTAKE_LINE = 4


@pytest.mark.parametrize(
    ("mistake", "said"),
    [
        ('pic.line("b", strat=(0, 0), end=(1, 1))', "line 'b' has no field 'strat'; did you mean"),
        ('pic.cirle("c", center=(0, 0), radius=1)', "there is no object type 'cirle'"),
        ('pic.add("nothing", "n")', "there is no object type 'nothing'"),
        ('pic.circle("a", center=(0, 0), radius=1)', "the id 'a' is taken already (by a line)"),
        ('pic.circle("c", center=(0, 0), radius=float("nan"))', "is not a finite number"),
        ('pic.circle("c", center=(0, 0), radius=1, label=label(tex="c", colour="a"))',
         "a label has no field 'colour'"),
        ("a.tpi", "'a' (line) has no anchor 'tpi'"),
        ('pic.measure_tex(r"\\frac{a}")', "TexError: "),
    ],
)  # fmt: skip
def test_the_message_ends_with_the_scripts_line_and_the_mistake(
    tmp_path: Path, header: dict[str, Any], mistake: str, said: str
) -> None:
    (tmp_path / "header.json").write_text(json.dumps(header), encoding="utf-8")
    (tmp_path / "build_ir.py").write_text(SCRIPT.format(mistake=mistake), encoding="utf-8")
    (issue,) = run_script(tmp_path, timeout=60)
    assert issue.code == "E-SCRIPT"
    assert f'build_ir.py", line {MISTAKE_LINE}, in <module>' in issue.message
    assert mistake in issue.message
    assert said in issue.message
    assert not any(name in issue.message for name in ("fields.py", "numbers.py", "_make"))


def test_only_the_scripts_mistakes_lose_the_sdks_frames() -> None:
    def deep() -> None:
        raise ScriptValueError("the id 'a' is taken already")

    def fault() -> float:
        return 1 / 0

    @at_the_call
    def mistake() -> None:
        deep()

    @at_the_call
    def broken() -> float:
        return fault()

    with pytest.raises(ScriptValueError) as caught:
        mistake()
    frames = [frame.name for frame in traceback.extract_tb(caught.value.__traceback__)]
    assert frames[-1] == "call" and "deep" not in frames
    with pytest.raises(ZeroDivisionError) as fault_caught:
        broken()
    frames = [frame.name for frame in traceback.extract_tb(fault_caught.value.__traceback__)]
    assert frames[-2:] == ["broken", "fault"]  # a fault in the SDK keeps its whole traceback
