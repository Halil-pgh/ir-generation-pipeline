"""Writes the JSON Schema of every contract into docs/spec/.

    make spec                                  # same as:
    python -m irpipe.schema.spec docs/spec

The pydantic models stay the only source of truth; these files are their
published form, for readers, other languages and the agent's prompt. A
test fails when a committed file no longer matches its model, so the
schemas cannot drift from the code.
"""

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from irpipe.core.report import Report
from irpipe.schema.brief import FrameBrief, LessonPlan
from irpipe.schema.ir import IRDocument
from irpipe.schema.lir import LIRDocument
from irpipe.schema.render_profile import RenderProfile
from irpipe.schema.request import PlannerRequest

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

CONTRACTS: dict[str, type[BaseModel]] = {
    "lesson_plan": LessonPlan,
    "brief": FrameBrief,
    "ir": IRDocument,
    "lir": LIRDocument,
    "render_profile": RenderProfile,
    "report": Report,
    "planner_request": PlannerRequest,
}
"""File stem -> model. ``ir`` is written as ``ir.schema.json``, and so on."""


def schema_of(model: type[BaseModel]) -> dict[str, Any]:
    return {"$schema": JSON_SCHEMA_DIALECT, **model.model_json_schema()}


def render(model: type[BaseModel]) -> str:
    """The schema as the text that goes into its file."""
    return json.dumps(schema_of(model), indent=2, ensure_ascii=False) + "\n"


def file_name(stem: str) -> str:
    return f"{stem}.schema.json"


def write_all(out_dir: Path) -> list[Path]:
    """Write every contract's schema into ``out_dir``; return the files written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for stem, model in CONTRACTS.items():
        path = out_dir / file_name(stem)
        path.write_text(render(model), encoding="utf-8")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m irpipe.schema.spec OUT_DIR", file=sys.stderr)
        return 2
    for path in write_all(Path(args[0])):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
