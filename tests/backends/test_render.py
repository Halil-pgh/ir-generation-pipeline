"""Stage "render": checks the LIR against the backend, then collects its files."""

from pathlib import Path
from typing import Any

import pytest

from irpipe.artifacts import LIR, OUT_DIR, RENDERED
from irpipe.backends.render import Render
from irpipe.core import Pipeline, RunResult, UnknownPluginError


def run(lir: Any, out_dir: Path, **options: Any) -> RunResult:
    pipeline = Pipeline([Render()], inputs=[LIR, OUT_DIR], options={"render": options})
    return pipeline.run({LIR: lir, OUT_DIR: out_dir})


def test_the_backends_files_are_handed_on(
    make_lir: Any, group: Any, line: dict[str, Any], tmp_path: Path
) -> None:
    result = run(make_lir(group("a", line)), tmp_path / "run", svg={"png": False})
    rendered = result.get(RENDERED)
    assert [p.name for p in rendered] == ["frame.svg"]
    assert (tmp_path / "run" / "frame.svg").exists()  # the folder is made when missing


def test_a_feature_the_backend_cannot_draw_stops_the_run(
    make_lir: Any, group: Any, tmp_path: Path
) -> None:
    formula = {
        "type": "math",
        "tex": "x^2",
        "size": 42,
        "color": "#FFFFFF",
        "at": [0, 0],
        "anchor": "center",
        "box": [-0.2, -0.1, 0.2, 0.1],
        "baseline": -0.05,
    }
    result = run(make_lir(group("f", formula)), tmp_path)
    assert result.stopped_at == "render"
    (issue,) = result.issues
    assert (issue.code, issue.objects) == ("E-CAPABILITY", ("f",))
    assert list(tmp_path.iterdir()) == []


def test_an_unknown_backend_is_named(make_lir: Any, tmp_path: Path) -> None:
    with pytest.raises(UnknownPluginError, match="unknown backend 'svgg'; did you mean 'svg'"):
        run(make_lir(), tmp_path, backend="svgg")
