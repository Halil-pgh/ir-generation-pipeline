"""What a run folder keeps besides the picture: meta.json and alt.txt (analysis §1).

    meta = meta_record(...)        # versions, tools, settings, timings: to draw it again
    text = alt_text(brief, ir)     # the picture in words, for people who cannot see it

meta.json names everything the picture depends on: the IR and LIR
versions, irpipe's, Python's, the backend's and its library's, the text
measurer and Pango's, LaTeX's and dvisvgm's, the font file fontconfig
picks, the stages that ran (with their times) and the header's hash.

alt.txt is written from the IR's intent, the brief's must_show items and
the words and formulas in the picture, with nothing made up.
"""

import importlib.metadata
import platform
import shutil
import subprocess
from collections.abc import Iterable, Sequence
from typing import Any

import irpipe
from irpipe.core import PipelineConfig, StageRun
from irpipe.schema.brief import FrameBrief
from irpipe.schema.ir import IRDocument, IRHeader, Math, Text, header_hash
from irpipe.schema.lir import LIR_VERSION


def meta_record(
    brief: FrameBrief,
    header: IRHeader,
    config: PipelineConfig,
    stages: Sequence[StageRun],
    status: str,
    started: str,
    seconds: float,
) -> dict[str, Any]:
    render = config.options.get("render", {})
    backend = str(render.get("backend", "svg"))
    measure = str(config.options.get("measure", {}).get("metrics", "pango"))
    return {
        "status": status,
        "started": started,
        "seconds": round(seconds, 3),
        "brief": {"id": brief.id, "lesson": brief.lesson, "version": brief.version},
        "ir": {"version": header.version, "header_hash": header_hash(header)},
        "lir": {"version": LIR_VERSION},
        "irpipe": irpipe.__version__,
        "python": platform.python_version(),
        "backend": {"name": backend, "library": _library(backend)},
        "reference": "svg" if backend != "svg" else None,
        "metrics": {"name": measure, "pango": _pango() if measure == "pango" else None},
        "tools": {tool: _first_line([tool, "--version"]) for tool in ("latex", "dvisvgm")},
        "fonts": {header.typography.text_font: _font_file(header.typography.text_font)},
        "math_font": header.typography.math,
        "pipeline": {"stages": [s.name for s in stages], "plugins": config.pipeline.plugins},
        "stage_seconds": {s.name: round(s.seconds, 3) for s in stages},
    }


def alt_text(brief: FrameBrief, document: IRDocument) -> str:
    """The picture in words: what it means, what it shows, the words and formulas in it."""
    lines = [_sentence(document.intent)]
    lines.append("It shows: " + "; ".join(item.text for item in brief.must_show) + ".")
    words, formulas = _written(document.objects)
    if words:
        lines.append("Words in it: " + "; ".join(f'"{w}"' for w in words) + ".")
    if formulas:
        lines.append("Formulas in it (TeX): " + "; ".join(formulas) + ".")
    return "\n".join(lines) + "\n"


def _written(objects: Iterable[Any]) -> tuple[list[str], list[str]]:
    """Every text and formula in the picture, labels included, once each, in file order."""
    words: dict[str, None] = {}
    formulas: dict[str, None] = {}
    for obj in objects:
        if isinstance(obj, Text):
            words[obj.text] = None
        elif isinstance(obj, Math):
            formulas[obj.tex] = None
        label = getattr(obj, "label", None)
        if label is not None:
            if label.text is not None:
                words[label.text] = None
            if label.tex is not None:
                formulas[label.tex] = None
    return list(words), list(formulas)


def _sentence(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else text + "."


def _library(backend: str) -> str | None:
    package = {"manim": "manim", "svg": "cairosvg"}.get(backend)
    if package is None:
        return None
    try:
        return f"{package} {importlib.metadata.version(package)}"
    except importlib.metadata.PackageNotFoundError:
        return None


def _pango() -> str | None:
    try:
        import pangocffi  # type: ignore[import-untyped]

        version = pangocffi.ffi.string(pangocffi.pango.pango_version_string())
        return f"Pango {version.decode()}"
    except Exception:  # the record says it does not know, rather than failing the run
        return None


def _first_line(command: list[str]) -> str | None:
    if shutil.which(command[0]) is None:
        return None
    try:
        out = subprocess.run(command, capture_output=True, check=False, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = out.stdout.decode(errors="replace").strip()
    return text.splitlines()[0] if text else None


def _font_file(family: str) -> str | None:
    return _first_line(["fc-match", "-f", "%{file}\n", family])
