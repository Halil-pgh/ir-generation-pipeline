"""Draws a scene.py with Manim, in its own process, and ties failures to IR objects.

    python -I -m irpipe.backends.manim.harness SCENE MANIFEST RESULT [--png FILE]
                                               [--media DIR] [--cache DIR]

The Manim backend writes scene.py and a manifest (each object's function,
variable and parts), then runs this harness (analysis §3). It imports
scene.py and calls every object's function on its own, parts first, so a
failure is reported with the object it belongs to. When every object can
be built, it renders ``Frame`` the way ``manim -s scene.py Frame`` does and
copies the picture to ``--png``. The generated code carries none of this.

The outcome goes to RESULT as JSON:

    {"failed": [{"id": "a", "kind": "internal", "message": "ValueError: ..."}],
     "error": null, "png": "frame.png"}

``kind`` is "environment" (Manim, LaTeX or a tool is missing) or "internal"
(a fault in the compiler). ``error`` is a failure of the whole run.

It runs in a process of its own because Manim keeps global state (its
config) and is slow to import; the pipeline imports neither.
"""

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ENVIRONMENT_ERRORS = (ImportError, FileNotFoundError)
MESSAGE_LIMIT = 600


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="irpipe.backends.manim.harness")
    parser.add_argument("scene", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("result", type=Path)
    parser.add_argument("--png", type=Path, help="where the picture goes; omit to only build")
    parser.add_argument("--media", type=Path, help="Manim's working folder")
    parser.add_argument("--cache", type=Path, help="where typeset formulas and texts are kept")
    args = parser.parse_args(argv)
    outcome = draw(args.scene, args.manifest, args.png, args.media, args.cache)
    args.result.write_text(json.dumps(outcome), encoding="utf-8")
    return 0


def draw(
    scene_file: Path,
    manifest_file: Path,
    png: Path | None,
    media: Path | None,
    cache: Path | None,
) -> dict[str, Any]:
    outcome: dict[str, Any] = {"failed": [], "error": None, "png": None}
    try:
        from manim import config
    except ImportError as exc:
        outcome["error"] = _problem(exc)
        return outcome
    if media is not None:
        config.media_dir = str(media)
    if cache is not None:
        config.tex_dir = str(cache / "Tex")
        config.text_dir = str(cache / "texts")
    config.verbosity = "WARNING"
    config.progress_bar = "none"
    config.disable_caching = True
    try:
        scene = _load(scene_file)
    except Exception as exc:  # Manim imported, so this is our scene.py or our call, not a tool
        outcome["error"] = {**_problem(exc), "kind": "internal"}
        return outcome
    objects = json.loads(manifest_file.read_text(encoding="utf-8"))["objects"]
    built: dict[str, Any] = {}
    for entry in objects:
        if not all(child in built for child in entry["children"]):
            continue  # a part of it failed and was reported
        try:
            make = getattr(scene, entry["function"])
            built[entry["variable"]] = make(*(built[child] for child in entry["children"]))
        except Exception as exc:
            outcome["failed"].append({"id": entry["id"], **_problem(exc)})
    if outcome["failed"] or png is None:
        return outcome
    try:
        frame = scene.Frame()
        frame.render()
        shutil.copyfile(frame.renderer.file_writer.image_file_path, png)
    except Exception as exc:
        outcome["error"] = _problem(exc)
        return outcome
    outcome["png"] = str(png)
    return outcome


def _load(scene_file: Path) -> ModuleType:
    """Import scene.py by its path; its top lines set Manim's config (frame, pixels)."""
    spec = importlib.util.spec_from_file_location("irpipe_scene", scene_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import {scene_file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _problem(exc: BaseException) -> dict[str, str]:
    kind = "environment" if isinstance(exc, ENVIRONMENT_ERRORS) else "internal"
    message = f"{type(exc).__name__}: {exc}".strip()
    if len(message) > MESSAGE_LIMIT:
        message = message[: MESSAGE_LIMIT - 3] + "..."
    return {"kind": kind, "message": message}


if __name__ == "__main__":
    raise SystemExit(main())
