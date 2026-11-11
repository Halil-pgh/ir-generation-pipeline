"""Regression: the examples drawn again and compared with their references; pictures compared;
a worker's pipeline.toml."""

import json
import shutil
import tomllib
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from irpipe.cli import main
from irpipe.core import load_config
from irpipe.evaluation import cases_in, regress
from irpipe.evaluation.configs import dump_toml, worker_config
from irpipe.evaluation.images import compare

ROOT = Path(__file__).parent.parent.parent


def picture(path: Path, *, mark: tuple[int, int, int, int] | None = None, size: int = 40) -> Path:
    """A dark square with a light bar; ``mark`` (left, top, right, bottom) painted red."""
    pixels = np.full((size, size, 3), 14, dtype=np.uint8)
    pixels[10:12, 5:35] = 230
    if mark is not None:
        left, top, right, bottom = mark
        pixels[top:bottom, left:right] = (255, 0, 0)
    Image.fromarray(pixels).save(path)
    return path


def test_pictures_are_the_same_up_to_antialiasing_and_otherwise_say_how_far(
    tmp_path: Path,
) -> None:
    reference = picture(tmp_path / "a.png")
    assert compare(reference, picture(tmp_path / "b.png")).same
    changed = compare(reference, picture(tmp_path / "c.png", mark=(0, 0, 4, 4)))
    assert not changed.same and (changed.strong, changed.ink) == (16, 76)
    assert changed.describe() == "16 of 76 ink pixels differ (21.05%), mean 2.410"
    changed.save(tmp_path / "difference.png")
    assert Image.open(tmp_path / "difference.png").size == (40, 40)
    other = compare(reference, picture(tmp_path / "d.png", size=50))
    assert not other.same and other.describe() == "size 50x50, reference 40x40"


@pytest.fixture
def examples(tmp_path: Path) -> Path:
    """Two of the repository's examples (one run, one render) and two folders that are not."""
    folder = tmp_path / "examples"
    for name in ("projection", "regions", "area_between", "lir"):
        shutil.copytree(ROOT / "examples" / name, folder / name)
    for reference in folder.glob("*/reference.png"):
        reference.unlink()
    return folder


def test_the_examples_are_drawn_compared_and_a_change_is_shown(
    examples: Path, tmp_path: Path, planner_config: Callable[..., Path]
) -> None:
    assert [(c.name, c.kind) for c in cases_in(examples)] == [
        ("projection", "run"), ("regions", "render"),
    ]  # fmt: skip
    config, out = planner_config(), tmp_path / "out"
    first = regress(examples, out, config_path=config, jobs=1, update=True)
    assert [(c.status, c.picture) for c in first.cases] == [("READY", "new")] * 2
    assert first.ok and (examples / "regions" / "reference.png").exists()
    again = regress(examples, out, config_path=config, jobs=2)  # in processes of their own
    assert [c.picture for c in again.cases] == ["same", "same"] and again.ready == 2
    ir = json.loads((examples / "regions" / "ir.json").read_text())
    ir["colors"] = {name: "#FF00FF" for name in ir["colors"]}
    (examples / "regions" / "ir.json").write_text(json.dumps(ir))
    changed = regress(examples, out, config_path=config, jobs=1)
    regions = changed.cases[1]
    assert regions.picture == "changed" and not changed.ok
    assert (
        regions.difference.endswith(tuple("0123456789"))
        and "ink pixels differ" in regions.difference
    )
    assert (out / "regions" / "difference.png").exists()
    written = json.loads((out / "regression.json").read_text())
    assert [c["picture"] for c in written] == ["same", "changed"]


def test_the_command_exits_1_on_a_change_and_0_after_an_update(
    examples: Path,
    tmp_path: Path,
    planner_config: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name in ("projection", "area_between", "lir"):
        shutil.rmtree(examples / name)
    args = ["regress", "--examples", str(examples), "-o", str(tmp_path / "out"), "--jobs", "1",
            "--config", str(planner_config())]  # fmt: skip
    assert main([*args, "--update"]) == 0
    assert main(args) == 0
    printed = capsys.readouterr().out.splitlines()
    assert printed[-2].startswith("regions: READY; picture same (")
    assert printed[-1] == f"1 of 1 READY -> {tmp_path / 'out' / 'regression.json'}"
    (examples / "regions" / "reference.png").write_bytes(picture(tmp_path / "x.png").read_bytes())
    assert main(args) == 1
    assert "picture changed: size 1920x1080, reference 40x40" in capsys.readouterr().out


def test_a_worker_gets_its_changes_its_own_manim_cache_and_the_examples_found(
    tmp_path: Path,
) -> None:
    changes = {"agent": {"model": "m"}, "options": {"render": {"backend": "svg"}}}
    path = worker_config(ROOT / "pipeline.toml", tmp_path / "w", tmp_path / "cache", changes)
    data = tomllib.loads(path.read_text())
    assert data["agent"]["model"] == "m" and data["options"]["render"]["backend"] == "svg"
    assert data["options"]["render"]["manim"]["cache_dir"].startswith(str(tmp_path / "cache"))
    assert data["planner"]["example"] == str(ROOT / "examples" / "projection")
    assert data["agent"]["example"] == str(ROOT / "examples" / "tangents" / "build_ir.py")
    whole = tomllib.loads((ROOT / "pipeline.toml").read_text())
    assert tomllib.loads(dump_toml(whole)) == whole
    assert load_config(path).options["check"] == whole["options"]["check"]
