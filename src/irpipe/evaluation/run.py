"""Running the eval matrix: every cell, many at once, and the folder that holds what came out.

    result = evaluate(Path("eval/lessons.toml"), Path("evals/lessons"), jobs=8)
    result.results, result.wall_seconds

The cells run in ``jobs`` processes at once (the matrix's ``jobs`` unless
given). Each cell plans, and draws with Manim, in a process of its own
(cells.py); a line is printed as each one ends. With one job the cells run
here, one after the other, which lets tests hand in scripted models.

The eval folder:

    matrix.toml          the eval file as it was run
    cells/<cell id>/     each cell: its pipeline.toml and its lesson folder
    results.json         every cell's numbers
    summary.md           the numbers put together (summary.py)
    gallery.html         every frame drawn, to look at
"""

import json
import shutil
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

from irpipe.agent import LLMClient
from irpipe.agent.sandbox import Sandbox
from irpipe.evaluation.cells import CellResult, run_cell
from irpipe.evaluation.matrix import read_matrix
from irpipe.evaluation.summary import gallery, summary


@dataclass(frozen=True)
class EvalResult:
    folder: Path
    results: list[CellResult]
    wall_seconds: float
    summary: str


def evaluate(
    matrix_path: Path,
    out: Path,
    *,
    config_path: Path = Path("pipeline.toml"),
    jobs: int | None = None,
    say: Callable[[str], None] = print,
    planner_client: LLMClient | None = None,
    agent_client: LLMClient | None = None,
    sandbox: Sandbox | None = None,
) -> EvalResult:
    """Run every cell of the eval file ``matrix_path`` into ``out``; an earlier run is replaced."""
    matrix = read_matrix(matrix_path)
    cells = matrix.cells()
    jobs = jobs or matrix.jobs
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    shutil.copy2(matrix_path, out / "matrix.toml")
    base = config_path.resolve()
    started = time.perf_counter()
    say(f"{len(cells)} cells, {min(jobs, len(cells))} at once -> {out}")
    results: list[CellResult] = []
    if jobs <= 1:
        for cell in cells:
            done = run_cell(cell, out, base, planner_client=planner_client,
                            agent_client=agent_client, sandbox=sandbox)  # fmt: skip
            results.append(done)
            say(_line(done, len(results), len(cells)))
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            running = [pool.submit(run_cell, cell, out, base) for cell in cells]
            for future in as_completed(running):
                results.append(future.result())
                say(_line(results[-1], len(results), len(cells)))
    order = {cell.id: n for n, cell in enumerate(cells)}
    results.sort(key=lambda r: order[r.cell.id])
    wall = time.perf_counter() - started
    text = summary(results, title=matrix_path.stem, wall_seconds=wall)
    data = [{**asdict(r), "ready": r.ready} for r in results]
    (out / "results.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    (out / "summary.md").write_text(text, encoding="utf-8")
    (out / "gallery.html").write_text(gallery(results, matrix_path.stem), encoding="utf-8")
    return EvalResult(out, results, round(wall, 1), text)


def _line(result: CellResult, done: int, total: int) -> str:
    cell = result.cell
    if result.error:
        said = result.error
    elif cell.draw:
        said = f"{result.ready} of {len(result.frames)} frames READY"
    else:
        said = f"{result.planned_frames} frames planned in {result.answers} answers"
    return (
        f"[{done}/{total}] {cell.id} {cell.topic!r}: {said}, ${result.cost_usd:.3f}, "
        f"{result.seconds:.0f} s"
    )
