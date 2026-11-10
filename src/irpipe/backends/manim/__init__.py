"""The Manim backend (analysis §3): LIR -> scene.py, and frame.png drawn by Manim.

scene.py is readable code that stands on its own: ``manim -s scene.py
Frame`` draws the picture. Every IR object is built by a function named
after its id, and Manim's own classes draw the shapes, texts and formulas,
at the places and sizes the front-end worked out.

frame.png is drawn by the harness (harness.py) in a process of its own. It
calls every object's function on its own first, so a failure names the IR
object it belongs to (E-DRAW, or E-ENVIRONMENT when a tool is missing).

What Manim cannot draw as the LIR says is lowered before it gets here:
quadratic curves (to cubics, exactly), dashes (to one path per dash, as
SVG lays them) and even-odd fills (Manim fills nonzero). Formulas are set
by Manim itself with the front-end's template, so ``math`` is drawn, not
lowered. Images are not drawn yet; the IR has no image object.

Settings, in pipeline.toml:

    [options.render.manim]
    png = true          # draw frame.png; false writes only scene.py
    timeout = 300       # seconds Manim may take
    cache_dir = ""      # typeset formulas and texts; default ~/.cache/irpipe/manim
"""

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from pydantic import PositiveFloat

from irpipe.backends.base import BACKENDS, E_ENVIRONMENT, Backend, Capability, Rendered
from irpipe.backends.manim.writer import Scene, to_scene
from irpipe.core import ISSUE_CODES, Issue, IssueCode, Origin
from irpipe.metrics.latex import MissingToolError
from irpipe.schema.base import StrictModel
from irpipe.schema.lir import LIRDocument

E_DRAW = ISSUE_CODES.register(
    IssueCode(
        "E-DRAW",
        Origin.INTERNAL,
        "the backend failed to draw an object: a fault in the compiler, not in the IR",
    )
)

HINT_INTERNAL = "a fault in the compiler, not in the IR; report it with scene.py"
HINT_MANIM = 'install the manim extra: pip install -e ".[manim]"'
HINT_TOOLS = (
    'check what Manim needs: the manim extra (pip install -e ".[manim]"), latex and dvisvgm, '
    "and the fonts the IR names"
)


class ManimOptions(StrictModel):
    png: bool = True
    timeout: PositiveFloat = 300
    cache_dir: str = ""


@BACKENDS.register
class ManimBackend(Backend):
    name = "manim"
    capabilities = frozenset(
        {Capability.CUBIC, Capability.TRANSFORM, Capability.TEXT, Capability.MATH}
    )
    options_model = ManimOptions

    def render(self, lir: LIRDocument, out_dir: Path) -> Rendered:
        try:
            from irpipe.backends.manim.ink import InkMetrics

            ink = InkMetrics()
        except MissingToolError as exc:
            return Rendered((), (E_ENVIRONMENT(f"texts cannot be placed: {exc}", hint=HINT_MANIM),))
        scene = to_scene(lir, ink.box)
        scene_file = out_dir / "scene.py"
        scene_file.write_text(scene.code, encoding="utf-8")
        if not self.settings.png:
            return Rendered((scene_file,))
        png = out_dir / "frame.png"
        issues = self._draw(scene, scene_file, png)
        files = (scene_file, png) if png.exists() and not issues else (scene_file,)
        return Rendered(files, tuple(issues))

    @property
    def settings(self) -> ManimOptions:
        assert isinstance(self.options, ManimOptions)
        return self.options

    def _draw(self, scene: Scene, scene_file: Path, png: Path) -> list[Issue]:
        """Run the harness on scene.py; what went wrong, in IR terms."""
        png.unlink(missing_ok=True)
        # The harness runs in the run folder, so every path it gets is absolute:
        # the run folder itself is often relative (runs/<name>).
        scene_file, png, cache = scene_file.resolve(), png.resolve(), self._cache().resolve()
        sources = {o.gid: o.source for o in scene.objects}
        with tempfile.TemporaryDirectory(prefix="irpipe-manim-") as folder:
            work = Path(folder)
            manifest = work / "manifest.json"
            objects = [o.entry() for o in scene.objects]
            manifest.write_text(json.dumps({"objects": objects}), encoding="utf-8")
            result = work / "result.json"
            command = [
                sys.executable, "-I", "-B", "-m", "irpipe.backends.manim.harness",
                str(scene_file), str(manifest), str(result), "--png", str(png),
                "--media", str(work / "media"), "--cache", str(cache),
            ]  # fmt: skip
            try:
                run = subprocess.run(
                    command,
                    cwd=scene_file.parent,
                    capture_output=True,
                    timeout=self.settings.timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return [
                    E_DRAW(
                        f"Manim took longer than {self.settings.timeout:g} s to draw the picture",
                        hint="raise [options.render.manim] timeout, or look for a heavy object",
                    )
                ]
            if not result.exists():
                said = run.stderr.decode(errors="replace").strip().splitlines()[-5:]
                return [E_DRAW(f"Manim stopped without an answer: {' / '.join(said)}")]
            outcome = json.loads(result.read_text(encoding="utf-8"))
        issues = [
            _issue(problem, objects=[problem["id"]], path=sources.get(problem["id"]))
            for problem in outcome["failed"]
        ]
        if outcome["error"] is not None:
            issues.append(_issue(outcome["error"]))
        return issues

    def _cache(self) -> Path:
        if self.settings.cache_dir:
            return Path(self.settings.cache_dir).expanduser()
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
        return Path(base) / "irpipe" / "manim"


def _issue(problem: dict[str, str], objects: Sequence[str] = (), path: str | None = None) -> Issue:
    """A harness failure as an issue: E-ENVIRONMENT for a missing tool, else E-DRAW."""
    what = f"'{objects[0]}'" if objects else "the picture"
    message = f"{what} could not be drawn: {problem['message']}"
    if problem["kind"] == "environment":
        return E_ENVIRONMENT(message, path=path, objects=objects, hint=HINT_TOOLS)
    return E_DRAW(message, path=path, objects=objects, hint=HINT_INTERNAL)
