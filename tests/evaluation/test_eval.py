"""The eval matrix with scripted models: its cells, a run, the numbers, the summary and gallery."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from irpipe.agent.sandbox import Sandbox
from irpipe.core.errors import PipelineConfigError
from irpipe.evaluation import evaluate, read_matrix

SUBMIT = '<call tool="submit"></call>'


def matrix(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "matrix.toml"
    path.write_text("[eval]\n" + text, encoding="utf-8")
    return path


def test_the_cells_are_topics_by_aspects_by_models_by_repeats(tmp_path: Path) -> None:
    path = matrix(tmp_path, 'topics = ["a", "b"]\naspects = ["16:9", "9:16"]\nrepeats = 2\n'
                  '[[eval.models]]\nplanner = "p1"\n[[eval.models]]\nagent = "a2"\n')  # fmt: skip
    cells = read_matrix(path).cells()
    assert len(cells) == 16 and len({c.id for c in cells}) == 16
    assert [c.id for c in cells[:3]] == ["t01-16x9-m1-r1", "t01-16x9-m1-r2", "t01-16x9-m2-r1"]
    assert (cells[0].planner, cells[0].agent) == ("p1", "claude-haiku-5-5")
    assert (cells[2].planner, cells[2].agent) == ("claude-sonnet-5-5", "a2")
    for bad, said in [
        ('topics = ["a"]\njbos = 2\n', "jbos: Extra inputs are not permitted"),
        ('topics = ["a"]\naspects = ["30:1"]\n', "outside the supported range"),
        ("topics = []\n", "topics: Tuple should have at least 1 item"),
    ]:
        with pytest.raises(PipelineConfigError, match=said):
            read_matrix(matrix(tmp_path, bad))


def test_an_eval_plans_and_draws_every_cell_and_sums_it_up(
    tmp_path: Path, planner_config: Callable[..., Path], scripted: Callable[..., Any], kit: Any
) -> None:
    path = matrix(tmp_path, 'topics = ["shadows", "vectors"]\nframes = 1\nbackend = "svg"\n')
    draw = [f'<call tool="run_python">\n{kit.SCRIPT}\n</call>', SUBMIT]
    lines: list[str] = []
    out = tmp_path / "eval"
    result = evaluate(
        path, out, config_path=planner_config(), jobs=1, say=lines.append,
        planner_client=scripted(kit.ONE, kit.ONE), agent_client=scripted(*draw, *draw),
        sandbox=Sandbox("audit"),
    )  # fmt: skip
    assert lines[0] == f"2 cells, 1 at once -> {out}"
    assert lines[1].startswith("[1/2] t01-16x9-m1-r1 'shadows': 1 of 1 frames READY, $0.030, ")
    first = result.results[0]
    assert (first.planned, first.lesson, first.answers, first.problems) == (
        True, "vector_projection", 1, 0,
    )  # fmt: skip
    frame = first.frames[0]
    assert (frame.frame, frame.status, frame.turns, frame.calls, frame.codes) == (
        "projection", "READY", 1, 2, (),
    )  # fmt: skip
    assert frame.picture == "cells/t01-16x9-m1-r1/lesson/runs/projection/frame.png"
    assert (out / frame.picture).exists()
    assert (first.planner_cost_usd, first.cost_usd) == (0.01, 0.03)
    summary = (out / "summary.md").read_text()
    assert "- Frames READY: 2 of 2 (100%)" in summary
    assert "- Cost: $0.06 (planner $0.02, agent $0.04)" in summary
    assert "| claude-sonnet-5-5 / claude-haiku-5-5 | 2 of 2 (100%) | 1.0 | 2.0 | 0.030 |" in summary
    assert (
        '<img src="cells/t02-16x9-m1-r1/lesson/runs/projection/frame.png"'
        in (out / "gallery.html").read_text()
    )
    written = json.loads((out / "results.json").read_text())
    assert [r["ready"] for r in written] == [1, 1] and (out / "matrix.toml").exists()


def test_a_plan_only_eval_counts_the_answers_and_a_failed_cell_does_not_stop_it(
    tmp_path: Path, planner_config: Callable[..., Path], scripted: Callable[..., Any], kit: Any
) -> None:
    path = matrix(tmp_path, 'topics = ["a", "b"]\nframes = 1\ndraw = false\n')
    planner = scripted("not JSON", kit.ONE, kit.LLMError("the network is down"))
    result = evaluate(
        path, tmp_path / "eval", config_path=planner_config(), jobs=1, say=lambda _: None,
        planner_client=planner,
    )  # fmt: skip
    planned, failed = result.results
    assert (planned.planned, planned.answers, planned.problems, planned.planned_frames) == (
        True, 2, 1, 1,
    )  # fmt: skip
    assert not failed.planned and failed.error.startswith("PlannerError: the planner's model")
    assert "| | planned | first answer usable | answers | frames | $ a plan | s a plan |" in (
        result.summary
    )
    assert "- Cells: 2; lessons planned: 1 of 2; usable at the planner's first answer: 0 of 2" in (
        result.summary
    )
    assert "## Cells that failed\n\n- t02-16x9-m1-r1 (b): PlannerError" in result.summary
