"""A pipeline.toml for one worker: the project's, with a few settings changed.

    path = worker_config(Path("pipeline.toml"), folder, cache, {"agent": {"model": "..."}})

Runs that go on at once each get their own copy, written into their
folder: the changes laid over the project's file, Manim's cache in a
folder of the worker's own (Manim writes typeset formulas and texts
without renaming them into place, so two runs typesetting the same formula
at once could read a half-written file), and the examples the planner's and
the agent's system prompts show made absolute, since they are read
relative to the file.
"""

import json
import os
import tomllib
from pathlib import Path
from typing import Any

from irpipe.agent.settings import AgentSettings
from irpipe.core import load_config
from irpipe.planner.settings import PlannerSettings


def worker_config(
    base: Path, folder: Path, cache: Path, changes: dict[str, Any] | None = None
) -> Path:
    """``base`` with ``changes`` laid over it, written as ``folder/pipeline.toml``."""
    data = tomllib.loads(base.read_text(encoding="utf-8"))
    config = load_config(base)
    examples = {
        "agent": AgentSettings.from_config(config).example,
        "planner": PlannerSettings.from_config(config).example,
    }
    for table, example in examples.items():
        if example and not Path(example).is_absolute():
            data.setdefault(table, {})["example"] = str((base.parent / example).resolve())
    data = _laid_over(data, changes or {})
    render = data.setdefault("options", {}).setdefault("render", {})
    render.setdefault("manim", {})["cache_dir"] = str(cache / f"manim-{os.getpid()}")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "pipeline.toml"
    path.write_text(dump_toml(data), encoding="utf-8")
    load_config(path)  # a change the config refuses fails here, in the worker
    return path


def dump_toml(data: dict[str, Any], prefix: str = "") -> str:
    """Tables of strings, numbers, booleans and lists of them, as TOML."""
    lines = [f"{key} = {_value(v)}" for key, v in data.items() if not isinstance(v, dict)]
    text = (f"[{prefix}]\n" if prefix and lines else "") + "".join(f"{line}\n" for line in lines)
    for key, value in data.items():
        if isinstance(value, dict):
            name = f"{prefix}.{key}" if prefix else key
            text += ("\n" if text else "") + dump_toml(value, name)
    return text


def _value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_value(item) for item in value) + "]"
    raise TypeError(f"cannot write {type(value).__name__} as TOML")


def _laid_over(below: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    result = dict(below)
    for key, value in over.items():
        under = result.get(key)
        both = isinstance(value, dict) and isinstance(under, dict)
        result[key] = _laid_over(under, value) if both else value  # type: ignore[arg-type]
    return result
