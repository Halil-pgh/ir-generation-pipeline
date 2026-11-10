"""The Manim backend drawing for real: the examples, ``manim -s``, failures and pixels.

These tests run Manim (and LaTeX), so they are marked ``manim`` and skipped
where Manim is not installed.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from irpipe.artifacts import IR, IR_SOURCE, LIR, OUT_DIR
from irpipe.backends.manim import ManimBackend
from irpipe.backends.manim.ink import InkMetrics
from irpipe.core import Pipeline, Report, RunResult, Status, load_config
from irpipe.core.plugins import load_plugins
from irpipe.schema.lir import Box, LIRDocument, MathItem, TextItem, walk_groups

if importlib.util.find_spec("manim") is None:
    pytest.skip("Manim is not installed", allow_module_level=True)

pytestmark = pytest.mark.manim

ROOT = Path(__file__).parent.parent.parent


def run_pipeline(text: str, out_dir: Path, cache: Path) -> RunResult:
    """The repository's pipeline.toml, drawing with Manim instead of the SVG backend."""
    config = load_config(ROOT / "pipeline.toml")
    load_plugins(config.pipeline.plugins)
    options = {name: dict(values) for name, values in config.options.items()}
    options["render"] = {"backend": "manim", "manim": {"cache_dir": str(cache)}}
    pipeline = Pipeline.build(config.pipeline.stages, inputs=[IR_SOURCE, OUT_DIR], options=options)
    return pipeline.run({IR_SOURCE: text, OUT_DIR: out_dir})


def report(result: RunResult) -> Report:
    allows = result.get(IR).allow if IR.name in result.artifacts else ()
    return Report.build(result.issues, allows=allows, stopped_at=result.stopped_at)


def pixels(path: Path) -> Any:
    return np.asarray(Image.open(path).convert("L")).astype(int)


def test_scene_py_runs_with_the_manim_command(tmp_path: Path) -> None:
    example = ROOT / "examples" / "projection" / "ir.json"
    out = tmp_path / "run"
    run_pipeline(example.read_text(encoding="utf-8"), out, tmp_path / "cache")
    manim = Path(sys.executable).parent / "manim"
    media = tmp_path / "media"
    command = [str(manim), "-s", "--media_dir", str(media), "scene.py", "Frame"]
    subprocess.run(command, cwd=out, capture_output=True, check=True, timeout=300)
    (png,) = media.glob("images/**/*.png")
    assert Image.open(png).size == (1920, 1080)
    difference = np.abs(pixels(png) - pixels(out / "frame.png"))
    assert difference.max() == 0  # the same picture the backend drew


def test_a_relative_run_folder_is_drawn_where_it_says(
    make_lir: Any, group: Any, line: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    out = Path("runs") / "line"  # `irpipe render` gives runs/<name>, relative
    out.mkdir(parents=True)
    rendered = ManimBackend({"cache_dir": "cache"}).render(make_lir(group("a", line)), out)
    assert rendered.issues == ()
    assert list(rendered.files) == [out / "scene.py", out / "frame.png"]
    assert sorted(p.name for p in out.iterdir()) == ["frame.png", "scene.py"]


def test_a_scene_that_cannot_be_loaded_is_a_fault_of_ours(tmp_path: Path) -> None:
    manifest, result = tmp_path / "manifest.json", tmp_path / "result.json"
    manifest.write_text('{"objects": []}', encoding="utf-8")
    harness = [sys.executable, "-I", "-B", "-m", "irpipe.backends.manim.harness"]
    paths = [str(tmp_path / "missing.py"), str(manifest), str(result)]
    subprocess.run([*harness, *paths], cwd=tmp_path, capture_output=True, check=True, timeout=300)
    error = json.loads(result.read_text(encoding="utf-8"))["error"]
    assert error["kind"] == "internal"  # not "install Manim": Manim is there
    assert error["message"].startswith("FileNotFoundError")


def test_a_failure_names_the_object_and_scene_py_is_still_written(
    make_lir: Any, group: Any, line: dict[str, Any], tmp_path: Path
) -> None:
    broken = {
        "type": "math",
        "tex": r"\fraq{1}{2}",  # the front-end would have caught it; the backend must cope
        "size": 42,
        "color": "#FFFFFF",
        "at": [0, 0],
        "anchor": "center",
        "box": [-0.2, -0.2, 0.2, 0.2],
        "baseline": 0,
    }
    drawing = make_lir(group("fine", line), group("f", broken, source="objects[3]"))
    backend = ManimBackend({"cache_dir": str(tmp_path / "cache")})
    rendered = backend.render(drawing, tmp_path)
    (issue,) = rendered.issues
    assert (issue.code, issue.objects, issue.path) == ("E-DRAW", ("f",), "objects[3]")
    assert issue.message.startswith("'f' could not be drawn: ")
    assert [p.name for p in rendered.files] == ["scene.py"]
    assert not (tmp_path / "frame.png").exists()


def ink_in_pixels(box: Box, lir: LIRDocument) -> tuple[float, float, float, float]:
    """A box in units as left, top, right, bottom pixels of the output frame."""
    (width, height), (units_w, units_h) = lir.canvas.pixels, lir.canvas.units
    kx, ky = width / units_w, height / units_h
    left, bottom, right, top = box
    cx, cy = width / 2, height / 2
    return (cx + left * kx, cy - top * ky, cx + right * kx, cy - bottom * ky)


def drawn_box(image: Any, around: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    """The box of the light pixels within 20 px of ``around``: left, top, right, bottom."""
    left, top = int(around[0]) - 20, int(around[1]) - 20
    right, bottom = int(around[2]) + 20, int(around[3]) + 20
    rows, cols = np.nonzero(image[top:bottom, left:right] > 128)
    return (left + cols.min(), top + rows.min(), left + cols.max() + 1, top + rows.max() + 1)


def test_texts_and_formulas_fill_the_boxes_the_front_end_measured(
    ir_text: Any, tmp_path: Path
) -> None:
    word = {"type": "text", "text": "Hxgy", "at": [-4, 1], "anchor": "left_baseline", "size": 64}
    bold = {"type": "text", "text": "Bold", "at": [-4, -2], "weight": "bold", "size": 52}
    formula = {"type": "math", "tex": r"\frac{a}{b} + \sqrt{x}", "at": [4, 0], "size": 64}
    objects = [{"id": "word", **word}, {"id": "bold", **bold}, {"id": "f", **formula}]
    out = tmp_path / "run"
    result = run_pipeline(ir_text(objects), out, tmp_path / "cache")
    assert report(result).status is Status.READY, report(result).issues
    lir = result.get(LIR)
    image = pixels(out / "frame.png")
    ink = InkMetrics()
    for group in walk_groups(lir.items):
        (item,) = group.children
        assert isinstance(item, TextItem | MathItem)
        box = ink.box(item) if isinstance(item, TextItem) else item.box
        assert box is not None
        expected = ink_in_pixels(box, lir)
        drawn = drawn_box(image, expected)
        assert np.allclose(drawn, expected, atol=1.5), (group.id, drawn, expected)


def test_strokes_scale_with_a_group_transform(make_lir: Any, group: Any, tmp_path: Path) -> None:
    def thickness(transform: list[float]) -> int:
        line = {
            "type": "path",
            "subpaths": [{"start": [-2, 0], "segments": [{"line": [2, 0]}]}],
            "stroke": {"color": "#FFFFFF", "width": 4},
        }
        drawing = make_lir(group("g", group("a", line), transform=transform))
        out = tmp_path / json.dumps(transform)
        out.mkdir()
        ManimBackend({"cache_dir": str(tmp_path / "cache")}).render(drawing, out)
        column = pixels(out / "frame.png")[:, 960]
        return int((column > 128).sum())

    assert thickness([1, 0, 0, 1, 0, 0]) == 4  # 4 reference px at 1080p
    assert thickness([2, 0, 0, 2, 0, 0]) == 8  # the group doubles it, as SVG does
