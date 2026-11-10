"""At the start: are the tools this picture needs installed? (analysis §1)

    issues = environment_issues(header, config)

A missing font, LaTeX, dvisvgm, LaTeX package or Python package is no
fault of the agent's and no fault of the planner's: the run stops before
the agent's script runs, and the issue (E-ENVIRONMENT) goes to a person.
"""

import importlib.util
import shutil
import subprocess
from collections.abc import Iterator

from irpipe.backends.base import E_ENVIRONMENT
from irpipe.core import Issue, PipelineConfig
from irpipe.metrics import fonts
from irpipe.schema.ir import IRHeader

TEX_FILES = ("standalone.cls", "lmodern.sty", "amsmath.sty", "amssymb.sty")
"""What the formula template needs from TeX Live (metrics/latex.py)."""

PACKAGES = {  # what each choice in pipeline.toml needs, and the extra that brings it
    ("measure", "pango"): ("pangocffi", "pango"),
    ("render", "manim"): ("manim", "manim"),
    ("render", "svg"): ("cairosvg", "svg"),
}


def environment_issues(header: IRHeader, config: PipelineConfig) -> list[Issue]:
    """Everything the picture needs that is not installed, as E-ENVIRONMENT issues."""
    return [*_font(header), *_tex(), *_packages(config)]


def _font(header: IRHeader) -> Iterator[Issue]:
    family = header.typography.text_font
    if not fonts.installed(family):
        yield E_ENVIRONMENT(
            f"the font '{family}' is not installed; texts would be set in a substitute",
            path="typography.text_font",
            hint=f"install {family}, or offer the planner a font pair that is installed",
        )


def _tex() -> Iterator[Issue]:
    for tool in ("latex", "dvisvgm"):
        if shutil.which(tool) is None:
            yield E_ENVIRONMENT(
                f"{tool} is not installed; formulas cannot be set",
                hint="install TeX Live (latex, with standalone, lmodern and amsmath) and dvisvgm",
            )
    if shutil.which("kpsewhich") is None:
        return
    for name in TEX_FILES:
        found = subprocess.run(["kpsewhich", name], capture_output=True, check=False, timeout=30)
        if found.returncode != 0 or not found.stdout.strip():
            yield E_ENVIRONMENT(
                f"TeX Live has no {name}; formulas cannot be set",
                hint=f"install the TeX Live package that brings {name}",
            )


def _packages(config: PipelineConfig) -> Iterator[Issue]:
    measure = config.options.get("measure", {}).get("metrics", "pango")
    render = config.options.get("render", {})
    backend = render.get("backend", "svg")
    wanted = [("measure", measure), ("render", backend)]
    if backend == "svg" and not render.get("svg", {}).get("png", True):
        wanted.remove(("render", "svg"))  # frame.svg alone needs no rasterizer
    for choice in wanted:
        if choice not in PACKAGES:
            continue
        package, extra = PACKAGES[choice]
        if importlib.util.find_spec(package) is None:
            yield E_ENVIRONMENT(
                f"{package} is not installed, and pipeline.toml chooses {choice[0]} = {choice[1]}",
                hint=f'install the {extra} extra: pip install -e ".[{extra}]"',
            )
